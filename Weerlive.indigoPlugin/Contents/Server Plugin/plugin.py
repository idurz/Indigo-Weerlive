# !/usr/bin/env python
# -*- coding: utf-8 -*-
##########################################################################################
#
#   An Indigo plugin for 
#     - reading (Dutch) Weather Information from weerlive.nl
#     - reading (Dutch) Rain precip from Buienradar
#     - reading UV index and foreacst from OpenUV.io
#     - calculating the Moonphase
#
#   Permission is hereby granted, free of charge, to any person
#   obtaining a copy of this software and associated documentation
#   files (the "Software"), to deal in the Software without
#   restriction, including without limitation the rights to use,
#   copy, modify, merge, publish, distribute, sublicense, and/or sell
#   copies of the Software, and to permit persons to whom the
#   Software is furnished to do so, subject to the following
#   conditions:

#   The above copyright notice and this permission notice shall be
#   included in all copies or substantial portions of the Software.

#   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
#   EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
#   OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
#   NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
#   HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
#   WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#   FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
#   OTHER DEALINGS IN THE SOFTWARE.
#
#   More info and contact details can be found on my website at
#   https://www.zengers.net/domotica/weerlive-plugin/
#
#   Version  History
#   -------  --------
#    0.9.0  June 8, 2020   First version based on FCIMweather
#    1.0.0  July 13, 2020  Preparing version for plugin Store
#    1.0.1  April 4, 2021  Version for Plugin store ready
##########################################################################################

try:
   import datetime
   import math
   import decimal
   import requests
   # import json
   # import shutil
   # import os.path
   import xml.dom.minidom
   libsOk = True
   dec = decimal.Decimal

except ImportError:
   libsOk = False


class Plugin(indigo.PluginBase):
##########################################################################################
#   Our Plugin Class
##########################################################################################

   def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
      ##########################################################################################
      #   (Required) Initalization of the indigo base plugin and on top of it our plugin
      ##########################################################################################
      indigo.PluginBase.__init__(self,pluginId,pluginDisplayName,pluginVersion,pluginPrefs)
      if not libsOk:
         self.logger.critical(u"Not all libraries could be loaded, this will lead to " +\
                               "errors while running; check your python environment")

      self.urlWL   = "https://weerlive.nl/api/json-data-10min.php"
      self.urlRT   = "https://gpsgadget.buienradar.nl/data/raintext"
      self.urlUV   = "https://api.openuv.io/api/v1/uv"
      self.urlUVfc = "https://api.openuv.io/api/v1/forecast"

      self.nxtWeerlive = datetime.datetime.min    # set next schedule moment for this device type
      self.nxtBuienradar = datetime.datetime.min 
      self.nxtUV = datetime.datetime.min 
      self.nxtMoon = datetime.datetime.min
      self.nxtuvforecast = datetime.datetime.min


      self.mplid = "com.fogbert.indigoplugin.matplotlib"

      # Define languages for moon phase descriptions. The last one is for the image name
      self.languages = { 'NL' : ["Nieuwe maan", "Wassende maansikkel", "Eerste kwartier", "Wassende maan", "Volle maan", 
                                 "Afnemende maan", "Laatste kwartier", "Afnemende maansikkel"]
                        ,'EN' : ["New Moon", "Waxing crescent", "First quarter", "Waxing gibbous", "Full Moon", 
                                 "Waning gibbous", "Last quarter", "Waning crescent"]
                        ,'image': ["new", "waxcr", "first", "waxgi", "full", "wangi", "last", "wancr"]
                  }

   def isNumber(self,numberToTest):
      ##########################################################################################
      #   Return true if this is a valid number
      ##########################################################################################
      try: #if it can be converted to a float, it's true
         float(numberToTest)
      except: # it it can't be converted to a float, it's false
         return False
      return True

   def __del__(self):
      ##########################################################################################
      #   (Required) This is the destructor for the class.
      ##########################################################################################
      indigo.PluginBase.__del__(self)

   def verbose(self, logtext):
      #########################################################################################
      #   My own logger
      ##########################################################################################
      loglevel = self.pluginPrefs.get("logLevel","Normal")
      if loglevel == "Verbose":
          self.logger.info(logtext)

   def actionControlUniversal(self, action, dev):
      ##########################################################################################
      #   General Action callback
      ##########################################################################################
      if action.deviceAction == indigo.kUniversalAction.Beep:
         txt = "beep"
      elif action.deviceAction == indigo.kUniversalAction.EnergyUpdate:
         txt = "energy update"
      elif action.deviceAction == indigo.kUniversalAction.EnergyReset:
         txt = "energy reset"
      elif action.deviceAction == indigo.kUniversalAction.RequestStatus:
         txt = "status"
      indigo.server.log(u"A {} request was received by {} which is not supported by this plugin".format(txt,dev.name))
      return

   def startup(self):
      ##########################################################################################
      #   After the init we can start our plugin. Define actions here
      ##########################################################################################
      self.logger.info("Starting %s Plugin; version %s" % (self.pluginDisplayName,self.pluginVersion))
      self.logger.info("For detailled logging, set level to Verbose in Plugin Config")

      # Check at startup if the device definition is changed
      for dev in indigo.devices.iter("self"):
         dev.stateListOrDisplayStateIdChanged()
      return

   def shutdown(self):
      ##########################################################################################
      #   Plugin is requested to shutdown
      ##########################################################################################
      self.verbose(u"Plugin shutdown requested.")

   def validateDeviceConfigUi(self, valuesDict, typeId, devId):
      ##########################################################################################
      #   Validation of device configuration input given.
      ##########################################################################################
      errorDict = indigo.Dict()
      self.verbose("Device Prefs have changed. Validating your input")

      if not self.isNumber(valuesDict["lat"]):
         errorDict["lat"] = "Lattitude is not numeric"
         return (False, valuesDict, errorDict)

      if not self.isNumber(valuesDict["lon"]):
         errorDict["lon"] = "Longitude is not numeric"
         return (False, valuesDict, errorDict)

      return (True, valuesDict)

   def validatePrefsConfigUi(self, valuesDict):
      ##########################################################################################
      #   Validation of plugin configuration input given.
      ##########################################################################################
      self.verbose("Plugin Prefs have changed. Validating your input")
      errorDict = indigo.Dict()

      if valuesDict["WeerLiveMode"]:
         if len(valuesDict["ApiKey"]) == 0:
            errorDict["ApiKey"] = "The ApiKey seems empty"
            return(False, valuesDict, errorDict)
         if not valuesDict["WeerLiveInterval"].isnumeric():
            errorDict["WeerLiveInterval"] = "Interval should be numeric" 
            return(False, valuesDict, errorDict)
         if int(valuesDict["WeerLiveInterval"]) < 10:
            errorDict["WeerLiveInterval"] = "Interval between measurements should be min. 10 minutes"
            return(False, valuesDict, errorDict)

      if valuesDict["UVindexMode"]:
         if len(valuesDict["UVApiKey"]) == 0:
            errorDict["UVApiKey"] = "The UVindex Access Token seems empty"
            return(False, valuesDict, errorDict)
         if not valuesDict["UVindexDailyMax"].isnumeric():
            errorDict["UVindexDailyMax"] = "Daily request max should be numeric" 
            return(False, valuesDict, errorDict)
         if int(valuesDict["UVindexDailyMax"]) < 1:
            errorDict["UVindexDailyMax"] = "Daily request max should be a positive number" 
            return(False, valuesDict, errorDict)

      try:
         time_param = datetime.strptime(valuesDict["uvforecastTime"],"%H:%M")
      except:
         errorDict["uvforecastTime"] = "-{}- Use time in 24-hour HH:MM format".format(valuesDict["uvforecastTime"])
         return(False, valuesDict, errorDict)
         
      if valuesDict["BuienradarMode"]:
         if not valuesDict["BuienRadarInterval"].isnumeric():
            errorDict["BuienRadarInterval"] = "Interval should be numeric" 
            return(False, valuesDict, errorDict)
         if int(valuesDict["BuienRadarInterval"]) < 10:
            errorDict["BuienRadarInterval"] = "Interval between measurements should be min. 10 minutes"
            return(False, valuesDict, errorDict)
         matplotlib_plugin = indigo.server.getPlugin(self.mplid)
         if valuesDict["PlotMode"] and not matplotlib_plugin.pluginVersion:
            errorDict["PlotMode"] = "Plugin MatPlotLib not found, cannot enable plot function"
            return(False, valuesDict, errorDict)

      dow = valuesDict["DaysOfWeek"].split(',')
      if len(dow) != 7:
         errorDict["DaysOfWeek"] = "Not all 7 days of the week are filled"
         return(False, valuesDict, errorDict)

      logLevel = valuesDict["logLevel"]
      if logLevel == "Verbose":
         self.logger.info("Verbose logging enabled")

      if logLevel == "Verbose":
         self.logger.info("Ended validatePrefsConfig succesfull")

      return (True, valuesDict)

   def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
      ##########################################################################################
      # Prefill device config UI with defaults before showing
      ##########################################################################################
      valuesDict = indigo.Dict(pluginProps)
      errorsDict = indigo.Dict()
      valuesDict["lat"], valuesDict["lon"] = indigo.server.getLatitudeAndLongitude()
      return (valuesDict, errorsDict)

   def utcToLocal(self,ts):
      ##########################################################################################
      # Convert received utc time string to local time string
      ##########################################################################################
      dt = datetime.datetime.strptime(ts,'%Y-%m-%dT%H:%M:%S.%fZ')
      tsv = (dt - datetime.datetime(1970, 1, 1)).total_seconds()
      d = datetime.datetime.utcfromtimestamp(tsv) # get the UTC time from the timestamp integer value.
      # calculate time difference from utcnow and the local system time reported by OS
      offset = datetime.datetime.now() - datetime.datetime.utcnow()
      return (d + offset) # Add offset to UTC time and return it

   def handle_weerlive(self,dev):
      ##########################################################################################
      # Get the lastest Weather information from Weerlive
      ##########################################################################################

      # -------------------
      # Set Next Run Moment
      # -------------------

      self.nxtWeerlive = datetime.datetime.now() + \
                               datetime.timedelta(minutes = int(self.pluginPrefs["WeerLiveInterval"]))
      self.verbose("Start Weerlive action now. Scheduled next run at {}".format(self.nxtWeerlive))
      dev.updateStateOnServer(key = "nextPlannedUpdate", 
                              value = self.nxtWeerlive.strftime("%Y-%m-%d %H:%M"))

      # -------------------
      # Request data
      # -------------------

      data = "{}?key={}&locatie={},{}".format(self.urlWL
                                             ,self.pluginPrefs["ApiKey"]
                                             ,dev.ownerProps["lat"]
                                             ,dev.ownerProps["lon"])
      self.verbose("Weerlive device {} is requesting {}".format(dev.name, data))

      try:
         r = requests.get(url = data)
      except requests.exceptions.RequestException as e:
        self.verbose("Weerlive Get ended with {}".format(e.code))
        return

      if not r.ok:
         self.verbose("Weerlive Get ended with code {}".format(r.status_code))
         return

      # -------------------
      # Parse result
      # -------------------

      try:
         rj = r.json()
      except:
         self.verbose("Weerlive could not decode the response into JSON")
         self.verbose(r.text)
         return

      # add the resulting json info to our states
      if "liveweer" in rj:
         for m in rj['liveweer']:
            for key in m:
               dev.updateStateOnServer(key = key, value = m[key])
               # reset alarm txt if no longer present
               if 'alarm' in m and m['alarm'] == '0':
                  dev.updateStateOnServer(key = 'alarmtxt', value = '')
      else:
         self.verbose("Weerlive result did not contain the expected 'weerlive' info")
         return

      # Update day of week
      moment = datetime.datetime.now()
      dow = self.pluginPrefs["DaysOfWeek"].split(',')

      dev.updateStateOnServer(key = "d0day", value = dow[moment.weekday()])
      moment = moment + datetime.timedelta(hours = 24)
      dev.updateStateOnServer(key = "d1day", value = dow[moment.weekday()])
      moment = moment + datetime.timedelta(hours = 24)
      dev.updateStateOnServer(key = "d2day", value = dow[moment.weekday()])
      
      # -------------------
      # Update and finish
      # -------------------
      
      dev.updateStateOnServer(key = "lastSuccessfullRun", 
                              value = datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
      self.verbose("Weerlive finished. Updated device")
      return


   def handle_buienradar(self,dev):
      ##########################################################################################
      # Get the lastest Weather information from Buienradar
      ##########################################################################################

      # -------------------
      # Set Next Run Moment
      # -------------------

      moment = datetime.datetime.now()
      self.nxtBuienradar = moment + datetime.timedelta(minutes = int(self.pluginPrefs["BuienRadarInterval"]))
      self.verbose("Start BuienRadar action now. Scheduled next run at {}".format(self.nxtBuienradar))
      dev.updateStateOnServer(key = "nextPlannedUpdate", 
                              value = self.nxtBuienradar.strftime("%Y-%m-%d %H:%M"))

      # -------------------
      # Request data
      # -------------------

      data = "{}?lat={}&lon={}".format(self.urlRT
                                      ,dev.ownerProps["lat"]
                                      ,dev.ownerProps["lon"])
      self.verbose("BuienRadar device {} is requesting {}".format(dev.name, data))

      try:
         r = requests.get(url = data)
      except requests.exceptions.RequestException as e:
         self.verbose("BuienRadar Get ended with {}".format(e.code))
         return

      if not r.ok:
         self.verbose("BuienRadar Get ended with code {}".format(r.status_code))
         return

      # -------------------
      # Parse result
      # -------------------

      # The rain next 10 minutes is 2 iterations, next hour is 12, next 2 hours is all
      sum10  = 0.0
      sum60  = 0.0
      sum120 = 0.0 
      fstr = ""

      hr = moment.hour
      hrBefore = moment.hour
      minBefore = moment.minute

      itercount = 0
      for l in r.text.splitlines():
         itercount += 1
         rainfall , raintime  = l.split("|")
         raintime = rainfall.strip()
         raintime = raintime.strip()

         if len(raintime) > 4 and raintime[0:2].isnumeric() and raintime[3:].isnumeric():
            hrBefore = int(raintime[0:2])
            minBefore = int(raintime[3:])

            if hrBefore < hr:
               # day change
               moment = moment + datetime.timedelta(days=1)
         nt = moment.replace(hour=hrBefore, minute=minBefore)
         hr = hrBefore

         intensiteit = 10 ** ((float(rainfall) - 109.0) / 32.0)

         # Add to running total
         if itercount < 3:
            sum10 += intensiteit
         if itercount < 13:
            sum60 += intensiteit
         sum120 += intensiteit 
         
         sum10 = round(sum10,1)
         sum60 = round(sum60,1)
         sum120 = round(sum120,1)

         # And to plot input file in memory
         fstr += "{},{}\n".format(nt,str(round(intensiteit,2)))
      
      dev.updateStatesOnServer([{'key' : 'rain10Minutes',  'value' : sum10, 'uiValue':"{} mm / 10 mn".format(sum10), 'decimalPlaces':1},
                                {'key' : 'rain60Minutes',  'value' : sum60, 'uiValue':"{} mm / hr".format(sum60), 'decimalPlaces':1},
                                {'key' : 'rain120Minutes', 'value' : sum120,'uiValue':"{} mm / 2 hr".format(sum120), 'decimalPlaces':1}])

      # 25 mm / uur is hoosbui


      # -------------------
      # Create CSV file
      # -------------------

      # if MATPLOTLIB is installed AND checked will serve a picture as well
      mpl = indigo.server.getPlugin(self.mplid)
      if "PlotMode" in self.pluginPrefs and self.pluginPrefs["PlotMode"] and mpl.isEnabled():

         self.verbose("BuienRadar found MatplotLib")
         # Check if we can open its plugin prefs file
         mpl_pluginConfig = indigo.server.getInstallFolderPath() + "/Preferences/Plugins/" + self.mplid + ".indiPref"
         try:
            doc = xml.dom.minidom.parse(mpl_pluginConfig)
            c = True
         except:
            self.verbose("BuienRadar Could not properly interpret " + mpl_pluginConfig)
            c = False
            # no need to continue
         
         if c:
            mpl_path = doc.getElementsByTagName("dataPath").item(0).firstChild.nodeValue
            self.verbose("BuienRadar Will store input file in {}".format(mpl_path))

            try:
               f = open("{}{}.buienradar.csv".format(mpl_path,self.pluginId), "w")
               c = True
            except:
               self.verbose("BuienRadar could not open for write {}{}.buienradar.csv".format(mpl_path,self.pluginId))
               c = False
               # no need to continue
         
            if c:
               # write file content 
               f.write("time,mm\n")
               f.write(fstr) # created earlier when fetching buienradar info
               f.close()
               self.verbose("BuienRadar Wrote {} bytes to {}{}.buienradar.csv".format(len(fstr),mpl_path,self.pluginId))

      # -------------------
      # Update and finish
      # -------------------
      
      dev.updateStateOnServer(key = "lastSuccessfullRun",value = datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
      self.verbose("BuienRadar finished. Updated device")
      return

   def handle_uvactual(self,dev):
      ##########################################################################################
      # Get current UV index from openuv.io
      ##########################################################################################

      # -------------------
      # Set Next Run Moment
      # -------------------

      moment = datetime.datetime.now()

      try:
         sunriseEnd = datetime.datetime.strptime(dev.states['sunriseEnd'],'%Y-%m-%d %H:%M')
         sunsetStart = datetime.datetime.strptime(dev.states['sunsetStart'],'%Y-%m-%d %H:%M')
         date_usable = True
      except:
         # date is not usable
         date_usable = False
         si = 30 # set default minutes

      # Check for daylight. To ensure we are always taling about the same, we remote, y,m,d here
      # since we are only interested in time. 
      if date_usable:
         moment_hhmm = moment.hour * 60 + moment.minute
         sunriseEnd_hhmm = sunriseEnd.hour * 60 + sunriseEnd.minute
         sunsetStart_hhmm = sunsetStart.hour * 60 + sunsetStart.minute
         if moment_hhmm > sunsetStart_hhmm:
            # Current time if after sunset 
            moment = moment + datetime.timedelta(days = 1) # tomorrow
            moment = moment.replace(hour=sunriseEnd.hour, minute=sunriseEnd.minute)
         else: 
            if moment_hhmm < sunriseEnd_hhmm:
               moment = moment.replace(hour=sunriseEnd.hour, minute=sunriseEnd.minute)

         sunUpDuration = sunsetStart_hhmm - sunriseEnd_hhmm # minutes sun is up
         si = int(round(float(sunUpDuration) / (float(self.pluginPrefs['UVindexDailyMax']) - 1),0))
      

      self.nxtUV = moment + datetime.timedelta(minutes = si)
      self.verbose("Start UVactual action now. Scheduled next run at {}".format(self.nxtUV))
      
      dev.updateStateOnServer(key = "nextPlannedUpdate", value = self.nxtUV.strftime("%Y-%m-%d %H:%M"))

      # -------------------
      # Request data
      # -------------------

      data = "{}?lat={}&lng={}".format(self.urlUV,dev.ownerProps["lat"], dev.ownerProps["lon"])
      headers = {'content-type' : 'application/json',
                'x-access-token': self.pluginPrefs["UVApiKey"]
                }

      self.verbose("UVactual device {} is requesting {}".format(dev.name, data))
      try: 
         r = requests.get(url = data, headers = headers)
      except requests.exceptions.RequestException as e:
         self.verbose("UVactual Get ended with {}".format(e.code))
         return

      if not r.ok:
         self.verbose("UVactual Get ended with code {}".format(r.status_code))
         self.verbose(r.text)
         return
 

      # -------------------
      # Parse result
      # -------------------

      try:
         rj = r.json()
      except:
         self.verbose("UVactual could not decode the response into JSON")
         self.verbose(r.text)
         return

      # result is expeced in the answer
      if not 'result' in rj:
         self.verbose("UVactual result did not contain the expected 'result' info")
         return
      res = rj['result']

      keyvalues = []
      if 'uv_time' in res and 'uv' in res:
         lcl = self.utcToLocal(res['uv_time'])
         keyvalues.append({'key' : 'uvtime', 'value'  : lcl.strftime("%Y-%m-%d %H:%M")})
         keyvalues.append({'key' : 'uvindex', 'value' : round(float(res['uv']), 2)})

         intuv = int(math.floor(float(res['uv'])))
         keyvalues.append({'key' : 'uvint', 'value' : intuv})
         if intuv > 10:
            uvname = 'Extreme'
         else:
            uvname = ['Low','Low','Low'                             #0-3
                     ,'Moderate','Moderate','Moderate'              #4-6
                     ,'High','High'                                 #6-8
                     ,'Very High','Very High','Very High'][intuv]   #8-11
         keyvalues.append({'key' : 'uvname', 'value' : uvname})

      if 'uvmax' in res:
         keyvalues.append({'key' : 'uvmax', 'value'  : round(float(res['uv_max']), 2)})
       
      if 'ozone' in res and 'ozone_time' in res:
         lcl = self.utcToLocal(res['ozone_time'])
         keyvalues.append({'key' : 'ozone', 'value' : res['ozone']})
         keyvalues.append({'key' :  'ozonetime', 'value' : lcl.strftime("%Y-%m-%d %H:%M")})

      if 'safe_exposure_time' in res: 
         se = res['safe_exposure_time']
         for x in range(1,7):
           if 'st{}'.format(x) in se:
              keyvalues.append({'key' : 'safe_st{}'.format(x), 'value' : se['st{}'.format(x)], 
                                'uiValue': '{} minutes'.format(se['st{}'.format(x)])})

      if 'sun_info' in res:
         si = res['sun_info']
         if 'sun_times' in si:
            st = si['sun_times']
            if 'sunriseEnd' in st:
               lcl = self.utcToLocal(st['sunriseEnd'])
               keyvalues.append({'key' : 'sunriseEnd', 'value' : lcl.strftime("%Y-%m-%d %H:%M")})
            if 'sunsetStart' in st:
               lcl = self.utcToLocal(st['sunsetStart'])
               keyvalues.append({'key' : 'sunsetStart', 'value' : lcl.strftime("%Y-%m-%d %H:%M")})
            if 'solarNoon' in st:
               lcl = self.utcToLocal(st['solarNoon'])
               keyvalues.append({'key' : 'solarNoon', 'value' : lcl.strftime("%Y-%m-%d %H:%M")})
            if 'night' in st:
               lcl = self.utcToLocal(st['night'])
               keyvalues.append({'key' : 'night', 'value' : lcl.strftime("%Y-%m-%d %H:%M")})

      # -------------------
      # Update and finish
      # -------------------
      
      keyvalues.append({'key' : 'lastSuccessfullRun', 'value' : datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
      dev.updateStatesOnServer(keyvalues)
      self.verbose("UVactual finished. Updated device")


   def handle_uvforecast(self,dev):
      ##########################################################################################
      # This function will retrieve forecast info from OpenUV.io
      #
      ##########################################################################################

      # -------------------
      # Set Next Run Moment
      # -------------------

      moment = datetime.datetime.now() # Get current time

      # Set next run time 
      #nexthr = int(self.pluginPrefs["uvforecastTime"][0:2])
      #nextmi = int(self.pluginPrefs["uvforecastTime"][3:])
      nexthr = 12
      nextmi = 8 
      self.nxtuvforecast = moment + datetime.timedelta(days = 1)
      self.nxtuvforecast = self.nxtuvforecast.replace(hour=nexthr, minute=nextmi, second=0)
      self.verbose("Start UVforecast action now. Scheduled next run at {}".format(self.nxtuvforecast))
      dev.updateStateOnServer(key = "nextPlannedUpdate", value = self.nxtuvforecast.strftime("%Y-%m-%d %H:%M"))

      # -------------------
      # Request data
      # -------------------

      data = "{}?lat={}&lng={}".format(self.urlUVfc,dev.ownerProps["fclat"], dev.ownerProps["fclon"])
      headers = {'content-type' : 'application/json',
                'x-access-token': self.pluginPrefs["UVApiKey"]
                }

      self.verbose("UVforecast device {} is requesting {}".format(dev.name, data))
      try: 
         r = requests.get(url = data, headers = headers)
      except requests.exceptions.RequestException as e:
         self.verbose("UVforecast Get ended with {}".format(e.code))
         return

      if not r.ok:
         self.verbose("UVforecast Get ended with code {}".format(r.status_code))
         self.verbose(r.text)
         return
 
      # -------------------
      # Parse result
      # -------------------

      try:
         rj = r.json()
      except:
         self.verbose("UVforecast could not decode the response into JSON")
         self.verbose(r.text)
         return

      # result is expeced in the answer
      if not 'result' in rj:
         self.verbose("UVforecast result did not contain the expected 'result' info")
         return
      res = rj['result']

      keyvalues = []
      # note time in utc
      maxuv = 0
      maxhr = 0
      for r in res:
         lcl = self.utcToLocal(r['uv_time'])
         thisuv = round(float(r['uv']),2)
         if thisuv > maxuv:
            maxuv = thisuv
            maxhr = lcl.hour
         keyvalues.append({'key' : 'UVForeCastHour_{0:02d}'.format(lcl.hour) ,'value' : thisuv})

      keyvalues.append({'key' : 'MaxExpected', 'value' : maxuv})
      keyvalues.append({'key' : 'MaxHour', 'value' : maxhr})   

      # -------------------
      # Update and finish
      # -------------------
      
      keyvalues.append({'key' : 'lastSuccessfullRun', 'value' : datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
      dev.updateStatesOnServer(keyvalues)
      self.verbose("UVforecast finished. Updated device")


   def handle_moonphase(self,dev):  
      ##########################################################################################
      # Calculate moonphase
      ##########################################################################################

      # -------------------
      # Set Next Run Moment
      # -------------------

      now = datetime.datetime.now() # Get current time

      # Set next run time
      self.nxtMoon = now + datetime.timedelta(minutes = 60)
      self.verbose("Start Moonphase action now. Scheduled next run at {}".format(self.nxtMoon))
      dev.updateStateOnServer(key = "nextPlannedUpdate", value = self.nxtMoon.strftime("%Y-%m-%d %H:%M"))
    
      # -------------------
      # Calculate
      # -------------------

      diff = now - datetime.datetime(2001, 1, 1)
      days = dec(diff.days) + (dec(diff.seconds) / dec(86400))
      lunations = dec("0.20439731") + (days * dec("0.03386319269"))
      pos = lunations % dec(1)

      index = (pos * dec(8)) + dec("0.5")
      index = math.floor(index)
      roundedpos = round(float(pos), 3)

      moonId = int(index) & 7

      # get moonphase and image description
      mylang = self.pluginPrefs.get("MoonLanguage","NL")

      # -------------------
      # Update and finish
      # -------------------

      dev.updateStatesOnServer([ {'key' : 'moonPhase',          'value'  : roundedpos}
                                ,{'key' : 'moonPhaseIcon',      'value'  : self.languages['image'][moonId]}
                                ,{'key' : 'moonIconIndex',      'value'  : moonId}
                                ,{'key' : 'moonPhaseName',      'value'  : self.languages[mylang][moonId]}
                                ,{'key' : 'lastSuccessfullRun', 'value'  : now.strftime("%Y-%m-%d %H:%M")
                                }])

      self.verbose("Moonphase finished. Updated device")
      return
      

   def runConcurrentThread(self):
      ##########################################################################################
      # This function will loop forever and only return after self.stopThread becomes True 
      #
      ##########################################################################################
      self.logger.info("Startup complete. Going in endless loop")
      try:
         while True: #  Until we are requested to stop

            moment = datetime.datetime.now()
            # Get a list of all defined devices for this plugin
            for dev in indigo.devices.iter("self"):

               # Check if we want to retrieve information for this type
               if (dev.deviceTypeId == "weerlive" and 
                  dev.enabled and
                  moment >= self.nxtWeerlive and
                  self.pluginPrefs["WeerLiveMode"]):
                  self.handle_weerlive(dev)

               # Check if we want to retrieve information for this type
               if (dev.deviceTypeId == "buienradar" and 
                  dev.enabled and 
                  moment >=self.nxtBuienradar and
                  self.pluginPrefs["BuienradarMode"]):
                  self.handle_buienradar(dev)

               # Check if we want to retrieve information for this type
               if (dev.deviceTypeId == "uv" and 
                  dev.enabled and 
                  moment >= self.nxtUV and
                  self.pluginPrefs["UVindexMode"]):
                  self.handle_uvactual(dev)

              # Check if we want to retrieve information for this type
               if (dev.deviceTypeId == "uvfc" and 
                  dev.enabled and 
                  moment >= self.nxtuvforecast and
                  self.pluginPrefs["uvforecastMode"]):
                  self.handle_uvforecast(dev)   

               # Check if we want to retrieve information for this type
               if (dev.deviceTypeId == "moon" and 
                  dev.enabled and 
                  moment >= self.nxtMoon and
                  self.pluginPrefs["MoonPhaseMode"]):
                  self.handle_moonphase(dev)   

            self.sleep(60)

      except self.StopThread:
         pass  # We will only arrive here after a plugin stop command

      return
