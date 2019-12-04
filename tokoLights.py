#!/usr/bin/env python
###################################################
# 
# this script allows to sync the illumination of a 3d printer controlled by octoprint
# with led strips controlled by an ESP8266 mcu. 
# 
# run - demonized or from console - 
# 
#
# 
# 


import paho.mqtt.client as mqtt #import the client1
import time
import ConfigParser
import string
import os
import sys
import json
import logging
from threading import Timer


reload(sys)
sys.setdefaultencoding('utf8')


def get_script_path():
    return os.path.dirname(os.path.realpath(sys.argv[0]))

def LoadConfig(file, config={}):
    """
    returns a dictionary with keys of the form
    <section>.<option> and the corresponding values
    """
    config = config.copy(  )
    cp = ConfigParser.ConfigParser(  )
    cp.read(file)
    for sec in cp.sections(  ):
        name = string.lower(sec)
        obj  = { }
        for opt in cp.options(sec):
            obj[string.lower(opt)] = string.strip(
                cp.get(sec, opt))
        config[name]=obj
    return config

    

def checkThings():
    return


class controllerClass(object):
    def __init__(self):
        self.initVars()
        self.active=False
        self.printerState="idle"
        self.tim = Timer(5, self.initialTimeout)
        self.tim.start()
        self.version="0.1.2"
        self.versionState="alpha"
          
    def initVars(self):
                
        self.phase='none'
        self.event="none"
        self.lowTemp=50.0
        self.highBedTemp=0.0
        self.highToolTemp=0.0
        self.actualBedTemp=0.0
        self.targetBedTemp=0.0
        self.actualToolTemp=0.0
        self.targetToolTemp=0.0
        self.printProgress=0
        self.isDuster=False
        self.da_jmd=False
        self.lux=0

        
    def initialTimeout(self):
        self.echo('controller: initial timer fired')
        self.setVal('active',True)
        self.tim=None
        
    def voidOut(self):
        self.initVars()
        self.tim=None
        self.tim2=None
    
    def setVal(self,kind,val):
        # at first start we may get a bunch of messages here that were retained in mqtt
        # only very few have relevance for this daemon so we filter the most of them by 
        # waiting some seconds before we go active
        if kind=='active':
            self.active=val
            
        if self.active:
            state='reads'
        else:
            state='ignores'
            
        # too much messages
        if kind== 'actualBedTemp' or kind=='targetBedTemp' or kind== 'actualToolTemp' or kind=='targetToolTemp':
            pass
        else:    
            self.echo("{} is {}".format(kind,val))

        # printerState is valid 
        if kind=='printerState':
            self.doPrinterState(val)


        if state=='ignores':
            return
            
        if kind=='event':
            self.doEvent(val)
        elif kind=='actualBedTemp':
            self.doBedTemp(val)
        elif kind=='targetBedTemp':
            self.doBedTempTarget(val)
        elif kind=='actualToolTemp':
            self.doToolTemp(val)
        elif kind=='targetToolTemp':
            self.doToolTempTarget(val)
        elif kind=='printProgress':
            self.doPrintProgress(val)
        elif kind=='isDuster':
            self.isDuster=val
        elif kind=='da_jmd':
            self.da_jmd=val 
        elif kind=='lux':
            self.lux=val 
        elif kind=='active':
            self.doActive()
            
    def doActive(self):
        # in init we let 1 msg through, printerState, as it is valid
        # even when a  leftover
        # now, active, we may have to act on it
        if self.active and self.printerState !="idle":
            self.doPrinterState(self.printerState)
        
    def doEvent(self,val):
        self.event=val
        if val=='Home':
            self.doPhase(val)
        elif val=='PrintDone':
            if conf['settings']['enable_autoshutoff_printer']:
                self.doShutOffPrinter()
        
    def doPrinterState(self,val):
        self.printerState=val
        if not self.active:
            return
        
        if val=='Operational':
            self.setStrip0(50)
            self.setStrip1(50)
            self.setRing('Operational')
            
        elif val=='Offline':
            self.setStrip0(0)
            self.setStrip1(0)
            self.setRing('Offline')
            
        elif val=='Starting':
            self.setStrip0(100)
            self.setStrip1(60)
            self.setRing('Starting')

        elif val=='Printing':
            self.setStrip0(200)
            self.setStrip1(100)
            self.setRing('Printing')
            

        # octoprint doesn't differentiate the actual printing
        # from it's preparation as a printerState. But we do.
        # Progressing while the printProgress advances 1 - 99
        elif val=='Progressing':
            self.setStrip0(1000)
            self.setStrip1(250)
            self.setRing('Progressing')
         
        elif val=='Finishing':
            self.setStrip0(150)
            self.setStrip1(70)
            self.setRing('Finishing')
            # auch eine Stelle, wo shutdown aufgerufen werden kann, falls printDone nicht erscheint
            self.doShutOffPrinter()

             
    def doPhase(self,val):
        if not self.phase==val:
            self.phase=val
            self.echo("new phase: {}".format(self.phase))
        
        if val=='Progressing':
            # Operational means, the printer is on and idle. No Progressing
            if self.printerState=='Operational' or self.printerState=='Offline':
                #gesangverein=runtime_error
                return
            if not self.printerState==val:
                self.doPrinterState(val)
         
    def doBedTemp(self,val):
        self.actualBedTemp=val
        
        # below lowTemp?
        if self.actualBedTemp < self.lowTemp:
            self.lowTemp = self.actualBedTemp
            self.echo("a new bed low: {}".format(val) )
        # beyond high        
        if self.actualBedTemp > self.highBedTemp:
            self.highBedTemp = self.actualBedTemp
            self.echo("a new bed high: {}".format(val) )
        # if heating, percent reached? (0 -> 100) and 0 ~ lowTemp
        # currently the values are negative when cooling
        if self.phase=='bedHeating':
            perc = (self.actualBedTemp-self.lowTemp)*100 / (self.targetBedTemp-self.lowTemp)
            self.doBedTempPercent(int(perc))
        # if cooling, percent gone down to (100 -> 0) and 0 ~ lowTemp
        if self.phase=='bedCooling':  
            perc = (self.actualBedTemp-self.lowTemp)*100 / (self.highBedTemp-self.lowTemp)
            self.doBedTempPercent(int(perc))
    
    
    def doBedTempTarget(self,val):
        if val > 0 and self.targetBedTemp==0:
            # bedHeating starts
            phase='bedHeating'
        elif val==0 and self.targetBedTemp>0:
            # bedCooling starts
            phase='bedCooling'
        
        self.targetBedTemp=val
            
        if phase:
            self.doPhase(phase)
    
    def doToolTemp(self,val):
        self.actualToolTemp=val
        # below lowTemp?
        if self.actualToolTemp < self.lowTemp:
            self.lowTemp = self.actualToolTemp
            self.echo("a new low: {}".format(val) )
        # beyond high        
        if self.actualToolTemp > self.highToolTemp:
            self.highToolTemp = self.actualToolTemp
            self.echo("a new tool high: {}".format(val) )
        # if heating, percent reached? (0 -> 100) and 0 ~ lowTemp
        # currently the values are negative when cooling
        if self.phase=='toolHeating' or self.phase=='bedHeatingDone':
            perc = (self.actualToolTemp-self.lowTemp)*100 / (self.targetToolTemp-self.lowTemp)
            self.doToolTempPercent(int(perc))
        # if cooling, percent gone down to (100 -> 0) and 0 ~ lowTemp
        if self.phase=='toolCooling' :
            perc = 100 - (self.highToolTemp-self.actualToolTemp-self.lowTemp)*100 / (self.highToolTemp-self.lowTemp)
            self.doToolTempPercent(int(perc))
        
        
    def doToolTempTarget(self,val):
        if val > 0 and self.targetToolTemp==0:
            # toolHeating starts
            phase='toolHeating'
        elif val==0 and self.targetToolTemp>0:
            # toolCooling starts
            # currently, bedCooling and toolCooling use the same control to show and since they overlap, it's either this or that.
            # uncomment the line below and the toolCooling drives the led ring temperature display
            #phase='toolCooling'
            pass
            
        self.targetToolTemp=val            

        if phase:
            self.doPhase(phase)
    
    
    def doBedTempPercent(self,perc):
        # ledRing {bed:percent} lower half of ring aqua -> magenta
        self.bedTempPercent=perc
        self.echo("bedTemp%: {}".format(perc) )
        self.setBedPerc(int(perc))
        if self.phase=='bedHeating' and perc > 97: # finetune with this threshold
            self.doPhase('bedHeatingDone')
        if self.phase=='bedCooling' or self.phase=='toolCooling':
            if perc < int(conf['settings']['ledring_threshold']):
                if not self.setRingOut:
                    self.echo( "setRing('Out')" )
                    # 'Out'     
                    self.setRing('Out')
                    self.setRingOut=True
    
    def doToolTempPercent(self,perc):
        # ledRing {tool:percent} upper half of ring aqua -> magenta
        self.toolTempPercent=perc
        self.echo("toolTemp%: {}".format(perc) )
        self.setToolPerc(int(perc))
        if self.phase=='toolHeating' and perc > 99: # finetune with this threshold
            self.doPhase('toolHeatingDone')


    def doPrintProgress(self,val):
        
        if val>0 and val<100:
            self.printProgress=val
            if self.printerState == Printing:
                if self.phase != 'Progressing':
                    self.doPhase('Progressing')
        
    def doShutOffPrinter(self):
        #should we?
        if not conf['settings']['enable_autoshutoff_printer']:
            return

        self.echo( "ShutOffPrinter called" )
        if conf['settings']['shutoff_delay_min']:
            # set up a timer with the asked delay and point it at 'setShutOffPrinter'
            delay=int(conf['settings']['shutoff_delay_min'])*60
            self.tim = Timer(delay, self.setShutOffPrinter)
            self.tim.start()
        
    def setShutOffPrinter(self):    
        # client_shutoff_topic 'OFF'
        self.echo( "ShutOffPrinter now" )
        msg='OFF'
        
        
        # sometimes the message does get through, sometimes it fails. 
        client_shutOff.publish(client_shutoff_topic,msg,1)
        time.sleep(.5)
        # issueing it twice
        client_shutOff.publish(client_shutoff_topic,msg)


        print(client_shutoff_topic,msg)
        self.doPhase('Ending') 

        
    def echo(self,val):
        # das kann dann zur Anzeige geschaltet werden, ueber settings.ini oder den controlKanal auf remote
        # logLevel, logPath, logToMqtt TBD
        if conf['settings']['enable_logging_to_console'].lower() == 'true':
            print(': {}'.format(val))
        if conf['settings']['enable_logging_to_file'].lower() == 'true':
            logging.info(val)
        
    
    def setStrip0(self,val):
        # mosquitto_pub -h kranich.intern -u spy -P autan -t led/tl/set -m '{"p0":10}'
        msg = '{"p0":'+str(val)+'}' 
        self.echo(msg) 
        
        client_remote.publish(client_remote_topic_control,msg,1)
        time.sleep(.5)
        # issueing it twice
        client_remote.publish(client_remote_topic_control,msg)


    def setStrip1(self,val):
        # mosquitto_pub -h kranich.intern -u spy -P autan -t led/tl/set -m '{"p0":10}'
        msg = '{"p1":'+str(val)+'}' 
        self.echo(msg) 
        client_remote.publish(client_remote_topic_control,msg,1)
        time.sleep(.5)
        # issueing it twice
        client_remote.publish(client_remote_topic_control,msg)


    def setRing(self,val):
        # this method was intended to accept many types of parameters,
        # however, only parts have been implemented yet
        if type(val) is str:
            json_string = None
            if val=='Operational':
               dict={"state":"ON","bright":12,"effect":"shiftBand","quart":23,"hueRange":10}
               json_string = json.dumps(dict)
            elif val=='Offline':
               dict={"state":"OFF"}
               json_string = json.dumps(dict)
            elif val=='Starting':
               dict={"state":"ON","bright":64,"effect":"shiftBand"}
               json_string = json.dumps(dict)

            elif val=='Out':
               dict={"bright":0}
               json_string = json.dumps(dict)
        
            if type(json_string) is str:
               client_remote.publish(client_remote_topic_control,json_string,1)
               time.sleep(.5)
               # issueing it twice
               client_remote.publish(client_remote_topic_control,json_string)



    def setBedPerc(self,val):
        # kelvin, 400 - 1400
        kelvin=10*val+400
        bright = int(kelvin/20) 
        dict={"state":"ON","bright":bright,"kelvin":kelvin}
        json_string = json.dumps(dict)
        client_remote.publish(client_remote_topic_control,json_string,1)
        


    def setToolPerc(self,val):
        # kelvin, 1400 - 2400
        kelvin=10*val+1400
        bright = int(kelvin/20)
        dict={"state":"ON","bright":bright,"kelvin":kelvin}
        json_string = json.dumps(dict)
        client_remote.publish(client_remote_topic_control,json_string,1)
        

    def octoPrintMsg(self,topic,msg):
        #print topic
        dMsg = json.loads(msg)
        #print("json: {}".format( dMsg ))
    
        # jetzt geht wirklich filament durchs system
        if topic == 'octoPrint/event/DisplayLayerProgress_feedrateChanged':
            if not self.active:
                return
            self.doPhase('Progressing') 
        
        if topic == 'octoPrint/event/DisplayLayerProgress':
            return

        if topic == 'octoPrint/event/PrinterStateChanged':
            self.setVal('printerState',dMsg.get('state_string'))

        elif topic == 'octoPrint/temperature/bed':
            #self.setBedTemp(dMsg.get('actual'),dMsg.get('target'))
            self.setVal('actualBedTemp',dMsg.get('actual'))
            self.setVal('targetBedTemp',dMsg.get('target'))

        elif topic.startswith('octoPrint/temperature/tool'):
            self.setVal('actualToolTemp',dMsg.get('actual'))
            self.setVal('targetToolTemp',dMsg.get('target'))

        elif topic == 'octoPrint/progress/printing':
            progress=dMsg.get('progress')
            # before start and after end we are not progressing
            if progress>0 and progress<100:
                self.setVal('printProgress',dMsg.get('progress'))

        elif topic == 'octoPrint/event':
            event = dMsg.get('_event')
            self.setVal('event',dMsg.get('_event'))
    
    
    def tokoLightsMsg(self,topic,msg):
        print("tokoLightsMsg: {}: {}".format(topic,msg))
        if topic == 'tokoLights/environ':
        # not yet used, meant to allow self-adapting WRT light level (duster==gloomy)
        # or presence of people (da == someone is present)
        # those values wd need to be supplied by some other program, example:
        # tokoLights/environ {"isDuster":"ON","da":"ON","lux":17}
            self.setVal('isDuster',dMsg.get('isDuster'))
            self.setVal('da_jmd',dMsg.get('da'))
            self.setVal('lux',dMsg.get('lux'))
        
        
        # lets be pingable
        elif topic == 'tokoLights/set/ping':
            self.echo("got ping, give pong")
            client_local.publish("tokoLights/state","pong")

        elif topic == 'tokoLights/set/dumpState':
            #print("dumpState!")
            dict=self.print_instance_attributes()
            
            json_string = json.dumps(dict)
            print json_string
            client_local.publish(client_remote_topic_pub,json_string)
    
    # help collect all properties
    def print_instance_attributes(self):
        dict={}
        for attribute, value in self.__dict__.items():
            dict[attribute]=value        
        return dict
        
# mqtt callbacks

def on_message_local(client, userdata, message):
    
    topic = message.topic
    msg = str(message.payload.decode("utf-8"))
    #print("incoming: {}: {}".format(topic,msg))

    if topic.startswith('octoPrint'):
        controller.octoPrintMsg(topic,msg)
        return
        
    elif topic.startswith('tokoLights'):
        print("message_local: {}: {}".format(topic,msg))
        controller.tokoLightsMsg(topic,msg)
        return
    else:
        self.echo("unknown {} \t {}".format(topic,msg))
        pass

# mqtt callbacks    

def on_message_remote(client, userdata, message):
    
    topic = message.topic
    msg = str(message.payload.decode("utf-8"))
    #print("incoming remote: {}: {}".format(topic,msg))
    dMsg = json.loads(msg)
    #print("incoming remote: {}: {}".format(topic,dMsg))


def on_connect_local(client_local, userdata, flags, rc):
    #print("local Connected with result code "+str(rc))
    if rc == 0:
        client_local.connected_flag=True
        client_local.subscribe(client_local_topic_feed)
        client_local.subscribe(client_local_topic_sub)
        client_local.publish(client_local_topic_pub,'{"state":"ON"}')
    else:
        controller.echo("local connect failed with result code "+str(rc))
        controller.echo("exiting")
        sys.exit()
        

def on_connect_remote(client_remote, userdata, flags, rc):
    #print("remote Connected with result code "+str(rc))
    if rc == 0:
        client_remote.connected_flag=True
    else:
        controller.echo("remote connect failed with result code "+str(rc))
        controller.echo("exiting")
        sys.exit()
        
def on_connect_shutOff(client_shutOff, userdata, flags, rc):
    #print("local Connected with result code "+str(rc))
    if rc == 0:
        client_shutOff.connected_flag=True
    else:
        controller.echo("shutOff connect failed with result code "+str(rc))
        controller.echo("exiting")
        sys.exit()
        
def on_disconnect(client, userdata, rc):
    #logging.info("disconnecting reason  "  +str(rc))
    client.connected_flag=False
    client.disconnect_flag=True
    
    

# begin
conf={}
conf=LoadConfig(get_script_path()+"/"+"settings.ini", conf)

# topics: the most important feeds on _local fromm the stream of octoprint messages
#         and on _remote one topic to control the mcu which does the lights
client_local_topic_feed  =conf['settings']['client_local_topic_feed'] 
client_remote_topic_control =conf['settings']['client_remote_topic_lightcontrol'] 

# on _local a pub/sub pair of channels to exchange messages with the script
# if only to check it's existence
client_local_topic_sub =conf['settings']['client_local_topic_sub'] 
client_local_topic_pub =conf['settings']['client_local_topic_pub'] 

# a topic to shut down the printer (via a tasmota switch or the likes)
client_shutoff_topic =conf['settings']['client_shutoff_topic']


# instantiate the controller class
controller = controllerClass()

# logging
logging.basicConfig(filename=conf['settings']['logpath'],level=logging.DEBUG,format='%(asctime)s %(message)s')
#logging.basicConfig(format='%(asctime)s %(message)s')
logging.info('Started')


# create the clients
# client_local lauscht am lokalen mqtt auf den stream von msg aus octoprint
# find a fairly unique clinet id
user_local=conf['settings']['user_local']
pwd_local= conf['settings']['pwd_local']
address_local=conf['settings']['address_local']
port_local=conf['settings']['port_local']

client_id="cl"+str(int(time.time()))
client_local = mqtt.Client(client_id)
client_local.connected_flag=False
client_local.on_connect = on_connect_local
client_local.on_disconnect = on_disconnect
client_local.on_message=on_message_local
client_local.username_pw_set(user_local,pwd_local)
client_local.connect(address_local, port_local, 60) 
client_local.loop_start()

# client_remote lauscht am remote mqtt auf evtl. Steuerungen
# hauptsaechlich dient er zum publish der lichtSteuerungen
user_remote=conf['settings']['user_remote']
pwd_remote= conf['settings']['pwd_remote']
address_remote=conf['settings']['address_remote']
port_remote=conf['settings']['port_remote']

client_id="cl"+str(int(time.time()))
client_remote = mqtt.Client(client_id)
client_remote.connected_flag=False
client_remote.on_connect = on_connect_remote
client_remote.on_disconnect = on_disconnect
client_remote.on_message=on_message_remote
client_remote.username_pw_set(user_remote,pwd_remote)
client_remote.connect(address_remote, port_remote, 60) 
client_remote.loop_start()


while not client_local.connected_flag: 
    time.sleep(.2)

while not client_remote.connected_flag: 
    time.sleep(.2)

if conf['settings']['enable_autoshutoff_printer']:
    user_shutOff=conf['settings']['user_shutoff']
    pwd_shutOff= conf['settings']['pwd_shutoff']
    address_shutOff=conf['settings']['address_shutoff']
    port_shutOff=conf['settings']['port_shutoff']

    client_id="cl"+str(int(time.time()))
    client_shutOff = mqtt.Client(client_id)
    client_shutOff.connected_flag=False
    client_shutOff.on_connect = on_connect_shutOff
    client_shutOff.on_disconnect = on_disconnect
    client_shutOff.username_pw_set(user_shutOff,pwd_shutOff)
    client_shutOff.connect(address_shutOff, port_shutOff, 60) 
    client_shutOff.loop_start()




try:
    # loop
    while 1:
        checkThings()
        time.sleep(.2)
except KeyboardInterrupt:
#except:
    print("\ncleaning up\n")
    client_local.publish(client_local_topic_pub,'{"state":"OFF"}')
    logging.info('Exiting')
    time.sleep(.1)
    client_local.loop_stop()
    client_remote.loop_stop()
    client_local.disconnect()
    client_remote.disconnect()
    if conf['settings']['enable_autoshutoff_printer']:
        client_shutOff.loop_stop()
        client_shutOff.disconnect()
    controller.voidOut()
    controller=None
    time.sleep(.3)
    