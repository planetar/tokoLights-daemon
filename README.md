# tokoLights-daemon

a script to sync the illumination on a 3d printer with the states of octoprint controlling that printer

tokoLights-daemon.py is a script meant to connect LED strips illuminating a 3d printer and controlled by an ESP8266 with the states of an octoPrint instance managing that printer. It relies on the stream of MQTT messages octoPrint generates with the help of the MQTT plugin as the input channel. On the output side it sends MQTT messages to a broker and topic where a corresponding led controller subscribed to that topic fetches them and then sets the lights accordingly.

In it's current setup tokoLights-daemon regards two single-color dimmable led-strips and a more complex WS2812 - strip as in his realm - i.e. a long strip at the extrusions of the printer and a short one close to the hotend plus a ring of neopixels at the pi cam. The script can also be used to turn off the printer after the print is done, provided something like a tasmota-switch is listening on a mqtt broker for this.

Then again, the script just reads and publishes mqtt messages and is completly agnostic about how the output is actually used.

The general environment for which the script was designed is a raspberry pi connected to a LAN/WLAN which manages an ender 3 printer attached to it by usb. The pi runs octopi with octoPrint and has a local mqtt broker. OctoPrint's MQTT plugin is configured to publish to that local broker (it is rather verbose and so I opted to keep those messages separate, but this is just my preference). tokoLights-daemon was created running on that same raspberry and thus regards the boker here to be 'local' while there is also a 'remote' broker where all the other smartHome appliances are subscribed. In the original setup this is on a different machine but this is arbitrary and if configured accordingly everything will run from a single broker.

Configuration of the tokoLights-daemon is done in the settings.ini file which has entries for three different clients (local, remote and shutOff) where the broker address, port, username and paswword and topics are set. It is settable whether auto shutOff of the printer should be attempted and how many minutes after 'print done' this should be, there is an option to how far the print bed must have cooled down to turn of the temperature-related led-ring. Logging can be dis/enabled and the filepath for it. 

The script can be run from the commandline but once all has been set to fit running it as a daemon is more comfortable. Daemonizing is easy with systemctl: adapt the script path in the file tokoLights.service to your choice, copy the saved file to /etc/systemd/system/tokoLights.service, systemctl enable tokoLights.service links it as a daemon, systemctl start tokoLights starts it and systemctl status tokoLights let's you check if it all worked out.

This is done in python 2.7, migration to python3 is still on the todo-list. This is beta.

There is a tokoLights-led.ino which I use for the nodemcu amica ESP8266 which runs the led-strips and to which the commands that tokoLights-daemon publishes are fine-tuned. It has it's own project page (TBD).
There are also two things on thingiverse that are related in a way: 
- the enclosure for a raspberry camera with attached led-ring https://www.thingiverse.com/thing:3984749 and 
- a rear column for the Ender 3 to attach the camera enclosure to https://www.thingiverse.com/thing:3978597


