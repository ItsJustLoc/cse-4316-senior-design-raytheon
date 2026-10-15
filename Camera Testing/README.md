# How to Operate the Cameras

# Requirements

The camera firmware requires a specific version of JetPack to work. Officially, the latest version supported is JetPack 6.2/L4T 36.5.0. If using NVIDIA SDK Manager, this is JetPack 6.2.2. Any version higher than 6.2.2 has not been tested and may not work.

#### Before running any of the commands below, make sure the JetPack SDK is fully up to date

Do this by running:

```text
sudo apt-get update
sudo apt-get install nvidia-jetpack
```

Also make sure the following tools are installed:
```text
sudo apt-get install i2c-tools
```

The official doccumentation also reccomends avoiding running `sudo apt-get upgrade`, however I have not had any issues after upgrading. 

# Step 1: Install Drivers

From the terminal:

```
wget https://github.com/ArduCAM/MIPI_Camera/releases/download/v0.0.3/install_full.sh
chmod +x install_full.sh
./install_full.sh -m imx519
```

Note that the install will throw an error at the end of its runtime if the current JetPack version is incompatable.

If the install was successful, the install should prompt you to restart the computer. 

## Step 2: Viewing the Cameras

Note: all 4 cameras **must** be connected to the add-on board before trying to display the camera feed.

First, confirm the board is reading as connected by trying `ls /dev/video0*` from the terminal.  
  
If everything worked as expected, a file path should be displayed. 

Run the following command:
```
gst-launch-1.0 nvarguscamerasrc sensor-id=0 ! "video/x-raw(memory:NVMM),width=1920,height=1080,framerate=60/1" ! nvvidconv ! "video/x-raw,format=I420" ! nveglglessink -e
```
The following command can be broken down into the following:  
- `sensor-id=0` 
    - This is the CSI port the board/camera is currently plugged into. The multiplexing board wrapps all 4 cameras into 1 output. Currently, the board is plugged into CSI port 0.
- `width=1920,height=1080,framerate=60/1`
    - This is the width, height, and framerate of the **raw** camera output. When the board combines the camera feeds together to display, each image is downscaled and shrunk to fit each feed into a 2x2 grid. However, when displaying each camera individually or taking a picture from each camera, the feed will be at its full specified resolution. More on how to select each camera individually will be covered later in this document.
    - The following is a list of all supported  resolutions and framerates.
        - 4656 x 3496 @ 9 FPS
        - 3840 x 2160 @ 17 FPS
        - 1920 x 1080 @ 60 FPS
        - 1280 x 720 @ 120 FPS



A window should be displayed showing each camera feed simultaneously. To exit, either close the window or ctrl+c in the terminal. 

## Changing the Displayed Camera

ArduCAM lists 3 options for camera output display: 1 Camera, 2 Cameras, and 4 Cameras. By default, the 4 Camera display is set. To change this, we need to modify the registry on the serial port the multiplexing board is running on. ArduCAM does not list the regestery edit required to change the board into 2 Camera display.  

To change the board into 1 Camera mode and display the desired camera, run the specified command in the terminal:
```
sudo i2cset -y 10 0x24 0x24 0x02 #Camera 0
sudo i2cset -y 10 0x24 0x24 0x12 #Camera 1
sudo i2cset -y 10 0x24 0x24 0x22 #Camera 2
sudo i2cset -y 10 0x24 0x24 0x32 #Camera 3
```
The `10` component is the i2c bus of the multiplexing board. Per ArduCAM's documentation, this value can either be `9` or `10`, however the board we are using runs on i2c bus `10`.

These commands can either be run prior to opening the camera feed or while it is open.

To switch the multiplexing board back to 4 Camera display, run:
```
sudo i2cset -y 10 0x24 0x24 0x00 #4-in-one display
```

## Example Program Integration
Included in `Picture` and `Autofocus` folders are example programs that I made or were provided by ArduCAM. The autofocus for the cameras are software driven so a basic autofocusing function is needed. More details on autofocusing are located in the `Autofocus` folder. 