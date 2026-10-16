This is an example program I generated to cycle through each camera individually, set a autofocus value, and take a picture. The file can be run by navigating to the location where the file is located in the terminal and running `python3 imx519_capture_all.py`.

The program will prompt what camera resolution to capture at given the list of valid capture resolutions. 

The program can take in the following flags:  
| Flag | Default | Description |
|---|---|---|
|`--bus N`|`10`|The i2c BUS the Multiplexing HAT is on|
|`--channels 0,1,2,3`|`0,1,2,3`|Which cameras to capture, in order|
|`--mode N`|Menu Prompt|Skip the menu prompt and select menu prompt `N`|
|`--focus N`|`275`|Exact focus value, from 0-1000|
|`--focus-min N`|`250`|Bottom of the focus range|
|`--focus-max N`|`300`|Top of the focus range. The exact focus value will be the midpoint between these value|
|`--out FOLDER`|`captures`|The destination folder where the pictures will be placed|
|`--video-dev PATH`|`/dev/video0`|The device path of the video feed|
|`--no-restore`|off|Determins whether the device is restored to 4-in-one camera mode|

In addition, the following global varables in the file can be modified to make the program take pictures faster or slower:
```
SWITCH_SETTLE_S
STREAM_START_S
FOCUS_SETTLE_S
EXPOSURE_SETTLE_S
```
