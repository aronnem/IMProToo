# -*- coding: utf-8 -*-
'''
ImProToo
Innominate MRR Processing Tool

Python toolkit to read and write MRR Data. Raw Data, Average and Instantaneous
Data are supported.

Copyright (C) 2011,2012 Maximilian Maahn, IGMK (mmaahn@meteo.uni-koeln.de)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

'''

import numpy as np
import gzip
import re
import datetime
import calendar
import time
import glob
from copy import deepcopy
import warnings
import sys

import IMProTooTools



class MrrZe:
  '''
  calculates the 'real' MRR Ze
  '''
  warnings.filterwarnings('always','.*', UserWarning,)

  def __init__(self,rawData):
    
    if rawData.mrrRawCC == 0:
      print('WARNING: MRR calibration constant set to 0!')
    
    self.co = dict()
    
    #verbosity
    self.co["debug"] = 0
    
    #MRR Settings
    #mrr frequency, MRR after 2011 (or upgraded) use 24.23e9
    self.co["mrrFrequency"] = 24.15e9 #in Hz,
    self.co["lamb"] = 299792458. / self.co["mrrFrequency"] #wavelength in m
    #mrr calibration constant
    self.co["mrrCalibConst"] = rawData.mrrRawCC

    #do not change these values, unless you have a non standard MRR!    
    #nyquist range minimum
    self.co["nyqVmin"] = 0
    #nyquist range maximum
    self.co["nyqVmax"] = 11.9301147
    #nyquist delta
    self.co["nyqVdelta"] = 0.1893669
    #list with nyquist velocities
    self.co["nyqVel"] = np.arange(self.co["nyqVmin"],self.co["nyqVmax"]+0.0001,self.co["nyqVdelta"])
    #spectral resolution
    self.co["widthSpectrum"] = 64
    #min height to be processed
    self.co["minH"] = 1 # start couning at 0
    #max heigth to be processed
    self.co["maxH"] = 31 # start couning at 0
    #no of processed heights
    self.co["noH"] = self.co["maxH"]+1 - self.co["minH"]
    #shape of spectrum for one time step
    self.co["specShape"] = (self.co["noH"],self.co["widthSpectrum"],)
    #input data MRR averageing time
    self.co["averagingTime"] = 10
    #|K**2| dielectric constant
    self.co["K2"] = 0.92

    
    #options for finding peaks
    
    #minimum width of a peak
    self.co["findPeak_minPeakWidth"] = 4
    #minimum signal to noise ratio = self.co["findPeak_minSnrCoeffA"]+self.co["findPeak_minSnrCoeffB"]/self.noSpecPerTimestep**1/2
    self.co["findPeak_minSnrCoeffA"] = 1.13 
    self.co["findPeak_minSnrCoeffB"] = 50 
    #minimum standard deviation of of spectrum for peak self.co["findPeak_minStdPerS"]/np.sqrt(self.co["averagingTime"])
    self.co["findPeak_minStdPerS"] = 0.6
    #minimum difference of doppler velocity from self.co["nyqVmax"]/2 for peak
    self.co["findPeak_minWdiff"] = 0.2
    
    
    
    #options for getting peaks    
    
    #method for finding peaks in the spectrum, either based on Hildebrand and Sekhon, 1974 [hilde] or on the method of descending average [descAve]. [hilde] is recommended
    self.co["getPeak_method"] = "hilde" #["hilde","descAve"]
    #sometimes the first method fails and almost the whole spectrum is found as a peak, so apply a second check based on the remaining method from [hilde,descAve]
    self.co["getPeak_makeDoubleCheck"] = True
    #apply double check to peaks wider than xx*noOfSpec
    self.co["getPeak_makeDoubleCheck_minPeakWidth"] = 0.9 #wider real peaks can actually happen! These are usually bimodal peaks, descending average method fails for them, thus the spectrum     
    #hilde method uses an extra buffer to avoid to large peaks. loop stops first at sepctrum >= self.co["getPeak_hildeExtraLimit"]*hilde_limit, only one more bin is added if above self.co["getPeak_hildeExtraLimit"]. More bins above self.co["getPeak_hildeExtraLimit"] are ignored
    self.co["getPeak_hildeExtraLimit"] = 1.2 #times hildebrand limit
    #options for descAve method
    #window to calculate the average, if too large, it might go into the next peak! if too small, it might not catch bimodal distributions
    self.co["getPeak_descAveCheckWidth"] = 10 
    #descAve stops not before mean is smaller than self.co["getPeak_descAveMinMeanWeight"] of the mean of the self.co["getPeak_descAveCheckWidth"] smallest bins. make very big to turn off
    self.co["getPeak_descAveMinMeanWeight"] = 4 
    
    #general options
    #process only peaks in self.co["spectrumBorderMin"][height]:self.co["spectrumBorderMax"][height]
    self.co["spectrumBorderMin"] = [5, 4, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 5]
    self.co["spectrumBorderMax"] =[60,61,62,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,63,62,61,63]
    #interpolate spectrum inbetween
    self.co["interpolateSpectrum"] = True
    #extend also peaks to interpolated part
    self.co["fillInterpolatedPeakGaps"] = True
    #mask everything in these heights, since they are disturbed
    self.co["completelyMaskedHeights"] = [0,1,30]
    #first height with trustfull peaks. Setting important for dealiasing to avoid folding from completelyMaskedHeights into the first used height.
    self.co["firstUsedHeight"] = 2
    
    #dealiasing options
    self.co["dealiaseSpectrum"] = True    
    #save also non dealiased eta, Ze, W, Znoise specWidth, peakLeftBorder, peakRightBorder
    self.co["dealiaseSpectrum_saveAlsoNonDealiased"] = True
    #make sure there is only one peak per heigth after deailiasing!
    self.co["dealiaseSpectrum_maxOnePeakPerHeight"] = True
    #dealiasing is based on comparison with reference velocity calculated from reflectivity. v = A*Ze**B
    self.co['dealiaseSpectrum_Ze-vRelationSnowA'] = 0.817 #Atlas et al. 1973
    self.co['dealiaseSpectrum_Ze-vRelationSnowB'] = 0.063 #Atlas et al. 1973
    self.co['dealiaseSpectrum_Ze-vRelationRainA'] = 2.6   #Atlas et al. 1973
    self.co['dealiaseSpectrum_Ze-vRelationRainB'] = 0.107 #Atlas et al. 1973
    
    #trusted peak needs minimal Ze
    self.co['dealiaseSpectrum_trustedPeakminZeQuantile'] = 0.1
    #if you have interference, you don't want to start you dealiasing procedure there
    self.co["dealiaseSpectrum_heightsWithInterference"] =  []
    #test coherence of dealiased velocity spectrum in time dimension. try to refold short jumps.
    self.co["dealiaseSpectrum_makeCoherenceTest"] = True
    #if the height averaged velocity between to timesteps is larger than this, it is tried to refold the spectrum
    self.co["dealiaseSpectrum_makeCoherenceTest_velocityThreshold"] = 8 
    #if there are after coherence test still velocity jumps, mask +/- timesteps
    self.co["dealiaseSpectrum_makeCoherenceTest_maskRadius"] = 10

    
    #netCDF options
    self.co["ncCreator"] = "M.Maahn, IGM University of Cologne"    
    self.co["ncDescription"] = ""    
    
    

    
    
    self.debugStopper = 0
    
    self.missingNumber = -9999.
    
    self.header = rawData.header
    self.time = rawData.mrrRawTime
    self.H = rawData.mrrRawHeight[:,self.co["minH"]:self.co["maxH"]+1]
    self.TF = rawData.mrrRawTF[:,self.co["minH"]:self.co["maxH"]+1]
    self.rawSpectrum = rawData.mrrRawSpectrum[:,self.co["minH"]:self.co["maxH"]+1]
    self.noSpecPerTimestep = rawData.mrrRawNoSpec
    
    self.no_h = np.shape(self.H)[1]
    self.no_t = np.shape(self.time)[0]
    self.no_v = self.co["widthSpectrum"]
    
    self._shape2D = np.shape(self.H)
    self._shape3D = np.shape(self.rawSpectrum)
        
    self.qual = dict()
        
    return  
      
  def averageSpectra(self,averagingTime):
    """
    average Spectras and other data. If averaging time is e.g. 60, the data with the timestamp 14:00 contains all measurements from 13:59:00 to 13:59:59 (like MRR standard software)
    """

    rawSpectra = self.rawSpectrum
    rawTimestamps = self.time
    heights = self.H
    TFs = self.TF
    noSpec = self.noSpecPerTimestep
    
    #find first entry
    startSeconds = IMProTooTools.unix2date(rawTimestamps[0]).second
    start = rawTimestamps[0] + averagingTime - startSeconds
    #find last minute
    endSeconds = IMProTooTools.unix2date(rawTimestamps[-1]).second
    end = rawTimestamps[-1] + 60 - endSeconds
    #make new timevector and 
    rawTimestampsAve = np.ma.arange(start,end+averagingTime,averagingTime,dtype="int")
    
    #create new arrays
    newSpectraShape = list(rawSpectra.shape)
    newSpectraShape[0] = rawTimestampsAve.shape[0]
    rawSpectraAve = np.ma.zeros(newSpectraShape) *np.nan 
    
    newTFsShape =  list(TFs.shape)
    newTFsShape[0] = rawTimestampsAve.shape[0]
    TFsAve = np.ma.zeros(newTFsShape) *np.nan

    newHeightsShape = list(heights.shape)
    newHeightsShape[0] = rawTimestampsAve.shape[0]
    heightsAve = np.ma.zeros(newHeightsShape) *np.nan
    
    newNoSpecShape = (rawTimestampsAve.shape[0],)
    noSpecAve = np.ma.zeros(newNoSpecShape,dtype=int) 
    
    
    #ugly loop trough new, averaged time vector!
    for t,timestamp in enumerate(rawTimestampsAve):
      #boolean array containing the wanted entries
      booleanTimes = (rawTimestamps<timestamp)*(rawTimestamps>=timestamp-averagingTime)
      aveLength = len(booleanTimes[booleanTimes==True])
      #proceed only if entries were found 
      if aveLength != 0 :
	# and if TF and heights are NOT changing and if heights are not zero!!
	if np.all(TFs[booleanTimes] == TFs[booleanTimes][0]) and np.all(heights[booleanTimes] == heights[booleanTimes][0]) and np.logical_not(np.all(heights[booleanTimes]==0)):
	  #averaging:
	  rawSpectraAve[t] = np.ma.average(rawSpectra[booleanTimes], axis=0)
	  heightsAve[t] = np.ma.average(heights[booleanTimes], axis=0)
	  TFsAve[t] = np.ma.average(TFs[booleanTimes], axis=0)
	  noSpecAve[t] = np.ma.sum(noSpec[booleanTimes])
	else:
	  print "Skipping data due to changed MRR configuration!"
      else:
	rawSpectraAve[t] = np.nan
	heightsAve[t] = np.nan
	TFsAve[t] = np.nan
	noSpecAve[t] = 0
	print "No Data at " + str(IMProTooTools.unix2date(timestamp))
    
    self.rawSpectrum = rawSpectraAve
    self.time = rawTimestampsAve
    self.H = heightsAve
    self.TF = TFsAve
    self.noSpecPerTimestep = noSpecAve.filled(0)

    self.no_t = np.shape(self.time)[0]    
    self._shape2D = np.shape(self.H)
    self._shape3D = np.shape(self.rawSpectrum)

    self.co["averagingTime"] = averagingTime
    return 
      
  def getSub(self,start,stop):
    """
    cut out some spectra (for debugging)
    """
    if stop == -1:
      stop = self._shape2D[0]
   
    self.rawSpectrum = self.rawSpectrum[start:stop]
    self.time = self.time[start:stop]
    self.H = self.H[start:stop]
    self.TF = self.TF[start:stop]
    self.noSpecPerTimestep = self.noSpecPerTimestep[start:stop]
    
    if len(self.noSpecPerTimestep) == 0:
      sys.exit('getSub: No data lef!')

    self.no_t = np.shape(self.time)[0]    
    self._shape2D = np.shape(self.H)
    self._shape3D = np.shape(self.rawSpectrum)

    return 
    
    
  def rawToSnow(self):


    self.untouchedRawSpectrum = deepcopy(self.rawSpectrum)
    
    self.specVel = self.co["nyqVel"]
    self.specVel3D = np.zeros(self._shape3D)
    self.specVel3D[:] = self.specVel

    self.specIndex = np.arange(self.no_v)
                
    self._specBorderMask = np.ones(self.co["specShape"],dtype=bool)
    for h in range(self.co["noH"]):
      self._specBorderMask[h,self.co["spectrumBorderMin"][h]:self.co["spectrumBorderMax"][h]] = False
    self._specBorderMask3D = np.ones(self._shape3D,dtype=bool)
    self._specBorderMask3D[:] = self._specBorderMask

    
    ##but we have to apply the TF before we start anything:
    TF3D = np.zeros(self._shape3D)
    TF3D.T[:] = self.TF.T
    self.rawSpectrum = np.ma.masked_array(self.rawSpectrum.data / TF3D,self.rawSpectrum.mask)
 
    #1)missing spectra
    missingMask = np.any(np.isnan(self.rawSpectrum.data),axis=-1)
    self.qual["incompleteSpectrum"] = missingMask
    #2) Wdiff
    WdiffMask, self.wdiffs = self._testMeanW(self.rawSpectrum)

    #3) std
    stdMask, self.stds = self._testStd(self.rawSpectrum)

    #join the results
    noiseMask = missingMask+(stdMask*WdiffMask)
    self.qual["spectrumVarianceTooLowForPeak"] = stdMask*WdiffMask #2) no signal detected by variance test

    #make 3D noise Mask
    noiseMaskLarge = np.zeros(self._shape3D,dtype=bool).T
    noiseMaskLarge[:] = noiseMask.T
    noiseMaskLarge = noiseMaskLarge.T

    #we don't need the mask right now since missingMask contains all mask entries
    self.rawSpectrum = self.rawSpectrum.data

    if self.debugStopper == 1:
      self.rawSpectrum = np.ma.masked_array(self.rawSpectrum,noiseMaskLarge)
      return
    #find the peak
    peakMask = np.ones(self._shape3D,dtype=bool)
    self.qual["usedSecondPeakAlgorithmDueToWidePeak"] = np.zeros(self._shape2D,dtype=bool)
    self.qual["peakTooThinn"] = np.zeros(self._shape2D,dtype=bool)
    for h in range(0,self.co["noH"]):
      #check whether there is anything to do
      if np.any(np.logical_not(noiseMaskLarge[:,h])):
	#get the peak
	specMins = self.co["spectrumBorderMin"][h]
	specMaxs = self.co["spectrumBorderMax"][h]
	peakMask[:,h,specMins:specMaxs][~noiseMask[:,h]],self.qual["peakTooThinn"][:,h][~noiseMask[:,h]],self.qual["usedSecondPeakAlgorithmDueToWidePeak"][:,h][~noiseMask[:,h]] = self._getPeak(self.rawSpectrum[:,h,specMins:specMaxs][~noiseMask[:,h]],self.noSpecPerTimestep[~noiseMask[:,h]],h)
    #apply results
    self.rawSpectrum = np.ma.masked_array(self.rawSpectrum,peakMask)
    if self.debugStopper == 2:  return
 
    #what is the noise, but _without_ the borders, we want in noise 3D also 
    noise = np.ma.masked_array(self.rawSpectrum.data,(np.logical_not(self.rawSpectrum.mask)+self._specBorderMask3D))
    self.specNoise = np.ma.average(noise,axis=-1).filled(0)

    #get the signal to noise ratio
    self.snr = np.max(self.rawSpectrum,axis=-1)/self.specNoise
    self.snr = self.snr.filled(0)
    #check whether snr Limit is exceeded
    #import pdb;pdb.set_trace()
    snrMask = (self.snr.T < (self.co["findPeak_minSnrCoeffA"]+self.co["findPeak_minSnrCoeffB"]/self.noSpecPerTimestep**1/2).T).T
    snrMask3D = np.zeros(self._shape3D,dtype=bool)
    snrMask3D.T[:] = snrMask.T
    self.rawSpectrum.mask = self.rawSpectrum.mask + snrMask3D
    self.qual["peakRemovedBySnrTest"] = snrMask #5) peak removed by snr test
    #check for coherence of the signal

    coherCheckNoiseMask = self._cleanUpNoiseMask(np.all(self.rawSpectrum.mask,axis=-1))
    coherCheckNoiseMask3D = np.zeros(self._shape3D,dtype=bool)
    coherCheckNoiseMask3D.T[:] = coherCheckNoiseMask.T
    self.qual["peakRemovedByCoherenceTest"] = coherCheckNoiseMask
    
    
    self.rawSpectrum.mask = self.rawSpectrum.mask + coherCheckNoiseMask3D
    if self.debugStopper == 3:  return
    
    #since we have removed more noisy spectra we have to calculate the noise again
    noise = np.ma.masked_array(self.rawSpectrum.data,(np.logical_not(self.rawSpectrum.mask)+self._specBorderMask3D))
    self.specNoise = np.ma.average(noise,axis=-1).filled(0)
    self.specNoise3D = np.zeros_like(noise).filled(0)
    self.specNoise3D.T[:] = self.specNoise.T

    
    #remove the noise
    self.rawSpectrum = np.ma.masked_array(self.rawSpectrum.data - self.specNoise3D, self.rawSpectrum.mask)

    if self.co["interpolateSpectrum"]:
      #interpolate spectrum
      intSpectrum = deepcopy(self.rawSpectrum.data)
      ix = np.arange(len(self.rawSpectrum.ravel()))
      intSpectrum[self._specBorderMask3D] = np.interp(ix[self._specBorderMask3D.ravel()], ix[~self._specBorderMask3D.ravel()], self.rawSpectrum[~self._specBorderMask3D])

      self.rawSpectrum = np.ma.masked_array(intSpectrum,self.rawSpectrum.mask)
      self.qual["interpolatedSpectrum"] = np.ones(self._shape2D,dtype=bool)
      if self.debugStopper == 5: return
    else:
      self.qual["interpolatedSpectrum"] = np.zeros(self._shape2D,dtype=bool)
    
    if self.co["fillInterpolatedPeakGaps"]:
      self.rawSpectrum.mask, self.qual["filledInterpolatedPeakGaps"] = self._fillInterpolatedPeakGaps(self.rawSpectrum.mask)
    else:
      self.qual["filledInterpolatedPeakGaps"] = np.zeros(self._shape2D,dtype=bool)

      
    if self.co["dealiaseSpectrum"] == True:
      
      if self.co["dealiaseSpectrum_saveAlsoNonDealiased"] == True:
	self.eta_noDA, self.Ze_noDA, self.W_noDA, self.Znoise_noDA, self.specWidth_noDA, self.peakLeftBorder_noDA, self.peakRightBorder_noDA = self._calcEtaZeW(self.rawSpectrum,self.H,self.specVel3D,self.specNoise)
	self.qual_noDA = deepcopy(self.qual)
	
      self.rawSpectrum = self._dealiaseSpectrum(self.rawSpectrum)
      #since we don't want that spectrum from teh disturbed 1st range gate are folded into the secod on, peaks in the second one might be incomplete. try to make an entry in the quality mask.
      self.qual["peakMightBeIncomplete"] = np.zeros(self._shape2D,dtype=bool)
      self.qual["peakMightBeIncomplete"][:,self.co["firstUsedHeight"]][self.rawSpectrum.mask[:,self.co["firstUsedHeight"],self.co["widthSpectrum"]+self.co["spectrumBorderMin"][self.co["firstUsedHeight"]]] == False ] = True
      
    else: 
      pass
    
    self.eta, self.Ze, self.W, self.Znoise, self.specWidth, self.peakLeftBorder, self.peakRightBorder = self._calcEtaZeW(self.rawSpectrum,self.H,self.specVel3D,self.specNoise)
    #maek bin mask out of quality information
    self.qualityBin, self.qualityDesc = self.getQualityBinArray(self.qual)
    return

  def _testMeanW(self,rawSpectrum):
    velocity = np.ma.masked_array(self.specVel3D,self._specBorderMask3D)
    
    mask = deepcopy(rawSpectrum.mask) + self._specBorderMask3D
    spec = np.ma.masked_array(rawSpectrum.data,mask)

    Wdiff=np.absolute(np.ma.average(velocity,axis=-1)-(np.ma.sum(velocity*spec,axis=-1)/np.sum(spec,axis=-1)))
    
    noiseMask = Wdiff.filled(0) < self.co["findPeak_minWdiff"]
    
    return noiseMask,Wdiff.filled(0)
    
  def _testStd(self,rawSpectrum):  
    
    mask = deepcopy(rawSpectrum.mask) + self._specBorderMask3D
    spec = np.ma.masked_array(rawSpectrum.data,mask)

    std = (np.ma.std(spec,axis=-1)/np.ma.mean(spec,axis=-1))
    
    maxStd =  self.co["findPeak_minStdPerS"]/np.sqrt(self.co["averagingTime"])
    
    return std.filled(0) < maxStd,std.filled(0)

  def _findAddtionalPeaks(self,rawSpectrum):
    '''
    This functio tries to find addtional peaks in the spectrum
    
    disabled since it gives too many false positives...
    
    '''
    qual = np.zeros(self._shape2D,dtype=bool)
    
    #invert mask
    rawSpectrum = np.ma.masked_array(rawSpectrum.data,~rawSpectrum.mask)
    self.co["findAddtionalPeaksThreshold"] = 15
    for tt in xrange(self.no_t):
      for hh in xrange(self.no_h):
	if hh in self.co["completelyMaskedHeights"]: continue
	greaterZero = 0
	for ii in xrange(self.co["spectrumBorderMin"][hh],self.co["spectrumBorderMax"][hh]):
	  if greaterZero >= self.co["findAddtionalPeaksThreshold"]:
	    qual[tt,hh] = True
	  if rawSpectrum.mask[tt,hh,ii] == True or rawSpectrum.data[tt,hh,ii] <= 0: 
	    greaterZero = 0
	    continue
	  else:
	    greaterZero += 1
    
    return qual
    
    
    
  def _cleanUpNoiseMask(self,noiseMask):
    """
    11 of 5x5 points in height/time space must have a signal to be valid!
    
    @parameter noiseMask (numpy boolean): noiseMask to be applied to teh data
    @return - noiseMask (numpy boolean):numpy boolean noiseMask
    """

    #to do: make it flexible depnedning of no of precessed heights
    
    newMask = deepcopy(noiseMask)  
    highLimit =11
    lowLimit = 9
    lowestLimit = 8
    hOffset = self.co["minH"]#since we don't start at zero height
    
    #loop through all points...
    for t in np.arange(noiseMask.shape[0]):
      #is it real signal? only if at least 11 of 25 neigbours have signal as well!
      for h in np.arange(4,28):
	if   noiseMask[t,h] == False:
	  subMask = noiseMask[t-2:t+3,h-2:h+3]
	  if len(subMask[subMask==False])<highLimit:
	    newMask[t,h] = True
      #treat the first and lastest height seperately! to avoid looking into disturbed, noisy bins
      for h in [29]:
	if   noiseMask[t,h] == False:
	  subMask = noiseMask[t-2:t+3,h-2:h+1]
	  if len(subMask[subMask==False])<lowestLimit:
	    newMask[t,h] = True
      for h in [2]:
	if   noiseMask[t,h] == False:
	  subMask = noiseMask[t-2:t+3,h:h+3]
	  if len(subMask[subMask==False])<lowestLimit:
	    newMask[t,h] = True
      #also the neighbours 
      for h in [28]:
	if   noiseMask[t,h] == False:
	  subMask = noiseMask[t-2:t+3,h-2:h+2]
	  if len(subMask[subMask==False])<lowLimit:
	    newMask[t,h] = True
      for h in [3]:
	if   noiseMask[t,h] == False:
	  subMask = noiseMask[t-2:t+3,h-1:h+3]
	  if len(subMask[subMask==False])<lowLimit:
	    newMask[t,h] = True

	
    #don't apply to the first and last two timesteps
    newMask[0:2] = noiseMask[0:2]
    newMask[-2:] = noiseMask[-2:]
    
    #kick out heights #0,1,30
    newMask[:,self.co["completelyMaskedHeights"]] = True
    
    self.qual["spectrumNotProcessed"] = np.zeros(self._shape2D,dtype=bool)
    self.qual["spectrumNotProcessed"][:,self.co["completelyMaskedHeights"]] = True
    
    return newMask
    
  def _getPeak(self,spectrum,noSpecs,h):
    """
    get the peak of the spectrum, first getPeakHildebrand is used, if the spectrum is wider than 10 and makeDoubleCheck = True, also getPeakDescendingAve is used and the smaller one is taken!
    
    @parameter spectrum (numpy float64): (averaged, dealiased) raw data from MRR Raw data
    @parameter noSpecs (numpy float64):number of single spectras which belong to each average spectrum, usually 58* No of averaged spectra
    @paramter h, (int): height, for easier debugging
    @return - spectrum (numpy float64): masked(!) spectrum
    @return - qualiy (dict with array bool)
    """
    t = time.time()
    quality = dict()
    
    specLength = np.shape(spectrum)[-1]
    #get maxima of reduced spectra
    iMax = np.argmax(spectrum,axis=-1)
    iMaxFlat = np.ravel(iMax)
    #arrays don't work, so make them flat
    spectrumFlat = np.reshape(spectrum,(-1,specLength))
    
    if self.co["getPeak_method"] == "hilde":
      #get peak using Hildebrands method
      firstPeakMask = self._getPeakHildebrand(spectrumFlat,iMaxFlat,noSpecs,h)
    elif self.co["getPeak_method"] == "descAve":
      #get peak using Hildebrands method
      firstPeakMask = self._getPeakDescendingAve(spectrumFlat,iMaxFlat)
    else: raise ValueError("Unknown doubleCheckPreference: "+  self.co["getPeak_method"])
    #import pdb;pdb.set_trace()
    
    peakMask = deepcopy(firstPeakMask)
    #look for wide peak and make a second check
    if self.co["getPeak_makeDoubleCheck"]:
      doubleCheck = np.sum(np.logical_not(firstPeakMask),axis=-1) > specLength * self.co["getPeak_makeDoubleCheck_minPeakWidth"]
      quality["veryWidePeakeUsedSecondPeakAlgorithm"] = doubleCheck
      if np.any(doubleCheck == True):
	#secondPeakMVeryWidePeakeUask = getPeakDescendingAve(spectrumFlat,iMaxFlat)
	secondPeakMask = np.zeros(np.shape(spectrumFlat),dtype=bool)
	if self.co["getPeak_method"] == "hilde":
	  #get peak using desc Average method
	  secondPeakMask[doubleCheck] = self._getPeakDescendingAve(spectrumFlat[doubleCheck],iMaxFlat[doubleCheck])
	elif self.co["getPeak_method"] == "descAve":
	  #get peak using Hildebrands method
	  secondPeakMask[doubleCheck] = self._getPeakHildebrand(spectrumFlat[doubleCheck],iMaxFlat[doubleCheck],noSpecs[doubleCheck],h)
	peakMask[doubleCheck] = firstPeakMask[doubleCheck] + secondPeakMask[doubleCheck]
    else:
      quality["veryWidePeakeUsedSecondPeakAlgorithm"] = np.zeros(specLength,dtype=bool)
    #only peaks which are at least 3 bins wide, remove the others
    tooThinn = np.sum(np.logical_not(peakMask),axis=-1) < self.co["findPeak_minPeakWidth"]
    peakMask[tooThinn] = True
    quality["peakTooThinn"] = tooThinn
    
    if self.co["debug"] > 0: print "runtime", time.time()-t,"s"
    return np.reshape(peakMask,np.shape(spectrum)), quality["peakTooThinn"],quality["veryWidePeakeUsedSecondPeakAlgorithm"]   #spectrum

  #get the border indices belonging to the hildebrand limit

  
  def _getPeakHildebrand(self,dataFlat,iMax,noSpecs,h):
    """
    get the peak of the spectrum using Hildebrand algorithm.
    
    @parameter dataFlat (numpy float64): flat spectrum from MRR Raw data
    @parameter iMax (numpy float64): vector containing indices of the maxima
    @parameter Nspec (numpy float64): number of spectra of each averaged spectrum

    @return - iPeakMin, iMax (int float64): edges of each spectrum
    """
    
    # first get the limit reflectivity
    limits = self._noiseHildebrand(dataFlat,noSpecs,h)
    maskHildebrand = np.ones(np.shape(dataFlat),dtype=bool)
    iPeakMax = deepcopy(iMax)
    iPeakMin = deepcopy(iMax)
    
    #import pdb; pdb.set_trace()
    #not only uses extra limit, but also starts at the peak!, thus specturm is refolded around peak!
    
    #then get the edges of the peak as index of the spectrum
    for k in np.arange(iMax.shape[0]):
      #unmask the peak
      maskHildebrand[k,iMax[k]] = False
      
      spectrum = np.roll(dataFlat[k],-iMax[k])
      mask = np.roll(maskHildebrand[k],-iMax[k])
      #to the right
      for i in np.arange(1,dataFlat.shape[-1],1):
	#unmask if above limit (=peak)
	if spectrum[i]>limits[k]*self.co["getPeak_hildeExtraLimit"]:
	  mask[i] = False
	#else stop
	else:
	  #unmask on last bin if between limits[k]*self.co["getPeak_hildeExtraLimit"] and limits[k], but stop in any case!
	  if spectrum[i]>limits[k]: 
	    mask[i] = False
	  break
      #to the left
      for i in np.arange(dataFlat.shape[-1]-1,0-1,-1):
	if spectrum[i]>limits[k]*self.co["getPeak_hildeExtraLimit"]:
	  mask[i] = False
	else:
	  if spectrum[i]>limits[k]: 
	    mask[i] = False
	  break

      dataFlat[k] = np.roll(spectrum,iMax[k])
      maskHildebrand[k] = np.roll(mask,iMax[k])	    
	    
    return maskHildebrand
    
    
    
    
  def _noiseHildebrand(self,dataFlat,noSpecs,h,flat=True):
    """
    #calculate the minimum reflectivity of the peak (or maximum of the noise) according to Hildebrand and Sekhon
    
    @parameter dataFlat (numpy masked array float64): flat spectrum from MRR Raw data
    @parameter Nspec (numpy float64): number of spectra of each averaged spectrum

    @return - limits (int float64): limit reflectivity of each spectrum
    """

    specLength = np.shape(dataFlat)[-1]
    if flat == False:
      dataShape = np.shape(dataFlat)[0]
      dataFlat = np.reshape(dataFlat,(-1,specLength))

    #sort the data
    dataFlat = np.ma.sort(dataFlat,axis=-1)
    
    #calculate all variances and means (that is cheaper than a loop!)
    #start with whole spectrum, then discard maximum, than second but next maximum etc.
    Dvar = np.zeros(dataFlat.shape)
    Dmean =  np.zeros(dataFlat.shape)
    limits = np.zeros(np.shape(dataFlat[...,0]))
    for i in np.arange(specLength-1,1,-1):
      Dvar[...,i] = np.ma.var(dataFlat[...,0:i],axis=-1)
      Dmean[...,i] = np.ma.mean(dataFlat[...,0:i],axis=-1)
    #calculate the Hildebrand coefficient
    Dvar[Dvar==0] = 0.0001
    Coefficient = ((Dmean**2) / Dvar)
    #check where hildebrands assumotion is true
    for j in np.arange(np.shape(dataFlat)[0]):
      #if everything is masked, cancel the loop
      #if Coefficient[j:j+1,-1].mask == True:
	#limits[j] = 0
      #else:
      for i in np.arange(specLength-1,-1,-1):
	if Coefficient[j,i] >= noSpecs[j]:
	  limits[j] = dataFlat[j,i-1]
	  break

    #import pdb; pdb.set_trace()
    if flat == False:
      limits = np.reshape(limits,(dataShape,self.co["noH"]))


    return limits
    
  def _getPeakDescendingAve(self,dataFlat,iMax):
    """
    get the peak of the spectrum
    function iterates through the _not_ size-sorted spectrum from the maximum to the left and to the right and stops as soon as the average stops decreasing.
    
    @parameter dataFlat (numpy float64): flat spectrum from MRR Raw data
    @parameter iMax (numpy float64): vector containing indices of the maxima

    @return - iPeakMin, iMax (int float64): edges of each spectrum
    """
    
    maskDescAve = np.ones(np.shape(dataFlat),dtype=bool)
    #pdb.set_trace()
    if "new" == "new":
      #iterate through spectras:
      for k in np.arange(iMax.shape[0]):
	#the rolling allow recognition also if 0 m/s is crossed
	rolledSpectrum = np.roll(dataFlat[k],-iMax[k])
	rolledMask = np.roll(maskDescAve[k],-iMax[k])
	#import pdb;pdb.set_trace()
	meanRightOld = np.ma.mean(rolledSpectrum[1:self.co["getPeak_descAveCheckWidth"]+1])
	meanLeftOld = np.ma.mean(rolledSpectrum[-1:-(self.co["getPeak_descAveCheckWidth"]+1):-1])
	minMeanToBreak = self.co["getPeak_descAveMinMeanWeight"] * np.mean(np.sort(dataFlat[k])[0:self.co["getPeak_descAveCheckWidth"]])
	#unmask peak
	rolledMask[0] = False
	#if k == 10: import pdb;pdb.set_trace()
	#to the right:
	for i in np.arange(1,dataFlat.shape[-1],1):
	  meanRight = np.ma.mean(rolledSpectrum[i:i+self.co["getPeak_descAveCheckWidth"]])
	  #is the average still decraesing?
	  if meanRight<=meanRightOld or meanRight > minMeanToBreak:
	    rolledMask[i] = False
	    meanRightOld = meanRight
	  else:
	    #apply threshold only if it is lower than twice the mean of the smalles bins!
	    #if meanRight > minMeanToBreak:
	      #rolledMask[i] = False
	      #meanRightOld = meanRight
	    #else:
	      break
	#to the left
	for i in np.arange(dataFlat.shape[-1]-1,0-1,-1):
	  meanLeft =  np.ma.mean(rolledSpectrum[i:i-self.co["getPeak_descAveCheckWidth"]:-1])
	  #is the average still decraesing?
	  if meanLeft<=meanLeftOld or meanLeft > minMeanToBreak:
	    rolledMask[i] = False
	    meanLeftOld = meanLeft
	  else:
	    #apply threshold only if it is lower than twice the mean of the smalles bins!
	    #if meanLeft > minMeanToBreak: 
	      #rolledMask[i] = False
	      #meanLeftOld = meanLeft
	    #else:
	      break
	dataFlat[k] = np.roll(rolledSpectrum,iMax[k])
	maskDescAve[k] = np.roll(rolledMask,iMax[k])
    else:
      #iterate through spectras:
      for k in np.arange(iMax.shape[0]):
	meanRightOld = np.ma.mean(dataFlat[k,iMax[k]:])
	meanLeftOld = np.ma.mean(dataFlat[k,:iMax[k]+1])
	maskDescAve[k,iMax[k]] = False
	
	#to the right:
	for i in np.arange(iMax[k]+1,dataFlat.shape[-1],1):
	  meanRight = np.ma.mean(dataFlat[k,i:])
	  #is the average still decraesing?
	  if meanRight<meanRightOld:
	    maskDescAve[k,i] = False
	    meanRightOld = meanRight
	  else:
	    break
	#to the left
	for i in np.arange(iMax[k]-1,0-1,-1):
	  meanLeft = np.ma.mean(dataFlat[k,:i+1])
	  #is the average still decraesing?
	  if meanLeft<meanLeftOld:
	    maskDescAve[k,i] = False
	    meanLeftOld = meanLeft
	  else:
	    break
    return maskDescAve

	
  def _fillInterpolatedPeakGaps(self, specMask):
    '''
    Interpolate gaps of specMask around 0 m/s between spectrumBorderMin and spectrumBorderMax in noH heights
    returns updated specMask and quality information
    '''
    quality = np.zeros(self._shape2D,dtype=bool)
    for h in xrange(1,self.co["noH"]):
      #the ones with peaks at both sides around 0 m/s!
      peaksAroundZero = (specMask[:,h-1,self.co["spectrumBorderMax"][h-1]-1] == False) * (specMask[:,h,self.co["spectrumBorderMin"][h]] == False)
      specMask[:,h,0:self.co["spectrumBorderMin"][h]][peaksAroundZero] = False
      specMask[:,h-1,self.co["spectrumBorderMax"][h-1]:][peaksAroundZero] = False
      
      #the ones with peak at only one side, 
      peaksAroundZeroHalfToLeft =  (specMask[:,h-1,self.co["spectrumBorderMax"][h-1]-1] == True) * (specMask[:,h,self.co["spectrumBorderMin"][h]] == False)
      peaksAroundZeroHalfToLeftBMin = (peaksAroundZeroHalfToLeft * (self.rawSpectrum.data[:,h,0:self.co["spectrumBorderMin"][h]] > self.specNoise3D[:,h,0:self.co["spectrumBorderMin"][h]]).T).T
      peaksAroundZeroHalfToLeftBMax = (peaksAroundZeroHalfToLeft * (self.rawSpectrum.data[:,h-1,self.co["spectrumBorderMax"][h-1]:] > self.specNoise3D[:,h,self.co["spectrumBorderMax"][h-1]:]).T).T
      specMask[:,h,0:self.co["spectrumBorderMin"][h]][peaksAroundZeroHalfToLeftBMin] = False
      specMask[:,h-1,self.co["spectrumBorderMax"][h-1]:][peaksAroundZeroHalfToLeftBMax] = False
      
      peaksAroundZeroHalfToRight = (specMask[:,h-1,self.co["spectrumBorderMax"][h-1]-1] == False) * (specMask[:,h,self.co["spectrumBorderMin"][h]] == True)
      peaksAroundZeroHalfToRightBMin = (peaksAroundZeroHalfToRight * (self.rawSpectrum.data[:,h,0:self.co["spectrumBorderMin"][h]] > self.specNoise3D[:,h-1,0:self.co["spectrumBorderMin"][h]]).T).T
      peaksAroundZeroHalfToRightBMax = (peaksAroundZeroHalfToRight * (self.rawSpectrum.data[:,h-1,self.co["spectrumBorderMax"][h-1]:] > self.specNoise3D[:,h-1,self.co["spectrumBorderMax"][h-1]:]).T).T
      specMask[:,h,0:self.co["spectrumBorderMin"][h]][peaksAroundZeroHalfToRightBMin] = False
      specMask[:,h-1,self.co["spectrumBorderMax"][h-1]:][peaksAroundZeroHalfToRightBMax] = False

      quality[:,h] = quality[:,h-1] = peaksAroundZero + peaksAroundZeroHalfToLeft + peaksAroundZeroHalfToRight
      
    return specMask,quality

    
  def _dealiaseSpectrum(self,rawSpectrum):
    '''
    dealiase Spectrum
    
    input rawSpectrum
    output extendSpectrum with 192 bins
    '''
    self.qual["severeProblemsDuringDA"] = np.zeros(self._shape2D,dtype=bool)
    
    #first locate peaks in raveld specturm
    self._allPeaks, self._allPeaksIndices, self._allPeaksMaxIndices, self._allPeaksVelMe, self._allPeaksHeight, self._allPeaksRefV, self._allPeaksZe = self._locatePeaks(rawSpectrum)
    
    #find one peaks and its veloci/heigth you trust
    self._trustedPeakNo, self._trustedPeakHeight, self._trustedPeakVel, self._trustedPeakHeightStart, self._trustedPeakHeightStop = self._getTrustedPeak(self._allPeaksZe,self._allPeaksVelMe,self._allPeaksRefV,self._allPeaksMaxIndices,self._allPeaksHeight)
    
    #self.qual["problemOcurredDuringDA"] = 0 catch the warnings and check for coherence within timestep
    #self.qual["spectrumIsHeavilyDealiased"] = 0 if velocity outof minus 2 plus 14?
    
    #now extend spectrum!
    extendedRawSpectrum = deepcopy(rawSpectrum.data)
    extendedRawSpectrum = np.concatenate((np.roll(extendedRawSpectrum,1,axis=1),extendedRawSpectrum,np.roll(extendedRawSpectrum,-1,axis=1)),axis=2)

    #do not apply fo first range gates
    extendedRawSpectrum[:,0,:self.co["widthSpectrum"]] = 0
    #and not to the last one
    extendedRawSpectrum[:,self.co["noH"]-1,2*self.co["widthSpectrum"]:]=0
    extendedRawSpectrum = np.ma.masked_array(extendedRawSpectrum,True)
    
    #if wanted, save old values
    if self.co["dealiaseSpectrum_saveAlsoNonDealiased"] == True:
      self.specVel_noDA = deepcopy(self.specVel)
      self.specVel3D_noDA = deepcopy(self.specVel3D)
      self.specIndex_noDA = deepcopy(self.specIndex)
      self.no_v_noDA = deepcopy(self.no_v)
      
    #save new velocities
    self.specVel = np.array(list(self.co["nyqVel"] - self.co["widthSpectrum"]*self.co["nyqVdelta"] )+list(self.co["nyqVel"])+list(self.co["nyqVel"] + self.co["widthSpectrum"]*self.co["nyqVdelta"] ))
    self.specVel3D = np.zeros(np.shape(extendedRawSpectrum))
    self.specVel3D[:] = self.specVel
    self.specIndex = np.arange(3*self.no_v)      
    self.no_v = self.no_v * 3
    
    #extend spectrum to 192 bins and unmask best fitting peaks
    extendedRawSpectrum = self._findHeightsForPeaks(extendedRawSpectrum,self._trustedPeakNo,self._trustedPeakVel,self._trustedPeakHeight,self._trustedPeakHeightStart,self._trustedPeakHeightStop,self._allPeaks, self._allPeaksIndices, self._allPeaksVelMe, self._allPeaksHeight)

    if self.co["dealiaseSpectrum_makeCoherenceTest"]:
      #simple method to detect falsely folded peaks, works only for 1-2 outliers
      extendedRawSpectrum = self._deAlCoherence2(extendedRawSpectrum)
    
    self.qual["spectrumIsDealiased"] = np.all(extendedRawSpectrum.mask[:,:,self.co["widthSpectrum"]:2*self.co["widthSpectrum"]] != rawSpectrum.mask[:,:],axis=-1)
    
    #still we don't want peaks at height 0,1,31
    extendedRawSpectrum.mask[:,self.co["completelyMaskedHeights"]] = True
    
    return extendedRawSpectrum
    
    
    
  def _locatePeaks(self,rawSpectrum):
    '''
    ravel rawSpectrum and try to find one peak per height
    
    returns time dictonaries with:
    allPeaks - time dictonary with lists of the spectral reflectivities for each peak
    allPeaksIndices - related indices
    allPeaksMaxIndices - time dictonary maximum of each peak
    allPeaksVelMe - first guess peak velocity based on the last bin
    allPeaksHeight - first guess peak height based on the last bin
    allPeaksRefV - expected velocity of each peak based on Ze according to theory
    allPeaksZe - time dictonary with lists of first guess Ze for each peak

    '''
    allPeaks = dict()
    allPeaksIndices = dict()
    allPeaksMaxIndices = dict()
    allPeaksVelMe = dict()
    allPeaksHeight = dict()
    allPeaksRefV = dict()
    allPeaksZe = dict()
    #get velocities of spectrum. we start negative, because first guess height is always defualt height of most right bin of peak
    velMe = np.array(list(self.co["nyqVel"] - self.co["widthSpectrum"]*self.co["nyqVdelta"] )+list(self.co["nyqVel"])) 
 
    for t in np.arange(self.no_t):
      completeSpectrum = self.rawSpectrum[t].ravel()

      #skip if there are no peaks in the timestep
      if np.all(completeSpectrum.mask) == True: 
	if self.co["debug"] > 4: '_locatePeaks: nothing to do at', t
	continue  
      
      deltaH = self.H[t,15] - self.H[t,14]
      
      peaks = list()
      peaksIndices= list()
      peaksMaxIndices = list()
      peaksVelMe = list()
      peaksHeight = list()
      peaksVref = list()
      peaksZe = list()
      
      peakTmp = list()
      peakTmpInd = list()
      peaksStartIndices=list()
      peaksEndIndices = list()
      
      #go through all bins
      for ii,spec in enumerate(completeSpectrum):
	#found peak!
	if completeSpectrum.mask[ii] == False:
	  peakTmp.append(spec)
	  peakTmpInd.append(ii)
	#3found no peak, but teh last one has to be processed
	elif len(peakTmp)>=self.co["findPeak_minPeakWidth"]:
	  #get the height of the LAST entry of the peak
	  peakTmpHeight = peakTmpInd[-1]//self.co["widthSpectrum"]
	  
	  #reconstruct the non folded indices shifted by 64! since peakTmpInd[-1] is reference
	  orgIndex = np.arange(peakTmpInd[-1]%self.co["widthSpectrum"]-len(peakTmpInd),peakTmpInd[-1]%self.co["widthSpectrum"])+1+self.co["widthSpectrum"]
	  
	  #calculate a first guess Ze
	  etaSumTmp = np.sum(peakTmp * np.array((self.co["mrrCalibConst"] * (peakTmpHeight**2 * deltaH)) / ( 1e20),dtype=float))
	  #in rare cases, Ze is below Zero, maybey since the wrong peak is examined?
	  if etaSumTmp<=0: 
	    warnings.warn('negative (linear) Ze occured during dealiasing, peak removed at timestep '+str(t)+', bin number '+ str(ii)+', most likely at height '+ str(peakTmpHeight))
	    self.qual["severeProblemsDuringDA"][t,peakTmpHeight] = True
	    peakTmp = list()
	    peakTmpInd = list()
	    continue
	  ZeTmp  = 1e18*(self.co["lamb"]**4*etaSumTmp/(np.pi**5*self.co["K2"]))
	  
	  #guess doppler velocity
	  peakTmpSnowVel =  self.co['dealiaseSpectrum_Ze-vRelationSnowA'] * ZeTmp**self.co['dealiaseSpectrum_Ze-vRelationSnowB']
	  peakTmpRainVel = self.co['dealiaseSpectrum_Ze-vRelationRainA'] * ZeTmp**self.co['dealiaseSpectrum_Ze-vRelationRainB']
	  peakTmpRefVel = (peakTmpSnowVel + peakTmpRainVel)/2.

	  #save other features
	  peaksVref.append(peakTmpRefVel)
	  peaks.append(peakTmp)
	  peaksIndices.append(peakTmpInd)
	  peaksStartIndices.append(peakTmpInd[0])
	  peaksEndIndices.append(peakTmpInd[-1])
	  
	  peaksMaxIndices.append(np.argmax(peakTmp)+ii-len(peakTmp))
	  peaksHeight.append(peakTmpHeight)
	  peaksVelMe.append(np.sum((velMe[orgIndex[0]:orgIndex[-1]+1]*peakTmp))/np.sum(peakTmp))
	  peaksZe.append(ZeTmp)	    
	  
	  peakTmp = list()
	  peakTmpInd = list()
	#small peaks can show up again due to dealiasing, get rid of them:
	elif len(peakTmp)>0 and len(peakTmp)<self.co["findPeak_minPeakWidth"]:
	  peakTmp = list()
	  peakTmpInd = list()
	#no peak
	else:
	  continue
	
      #we want only ONE peak per range gate!
      if self.co["dealiaseSpectrum_maxOnePeakPerHeight"]:
	#get list with peaks, whcih are too much
	peaksTbd = self._maxOnePeakPerHeight(t,peaksStartIndices,peaksEndIndices,peaksZe)
	#remove them
	for peakTbd in np.sort(peaksTbd)[::-1]:
	  peaks.pop(peakTbd)
	  peaksIndices.pop(peakTbd)
	  peaksMaxIndices.pop(peakTbd)
	  peaksVelMe.pop(peakTbd)
	  peaksHeight.pop(peakTbd)
	  peaksVref.pop(peakTbd)
	  peaksZe.pop(peakTbd)

      #if anything was found, save it
      if len(peaks) > 0:
	allPeaks[t] = peaks
	allPeaksIndices[t] = peaksIndices
	allPeaksMaxIndices[t] = peaksMaxIndices
	allPeaksVelMe[t] = peaksVelMe
	allPeaksHeight[t] = peaksHeight
	allPeaksRefV[t] = peaksVref
	allPeaksZe[t] = peaksZe
    #end for t
	
    return allPeaks, allPeaksIndices, allPeaksMaxIndices, allPeaksVelMe, allPeaksHeight, allPeaksRefV, allPeaksZe

  def _maxOnePeakPerHeight(self,t,peaksStartIndices,peaksEndIndices,peaksZe):
    '''
    some height will contain more than one peak, try to find them
    returns a list with peaks to be delteted
    '''
    
    peaksStartIndices = np.array(peaksStartIndices)
    peaksEndIndices = np.array(peaksEndIndices)
    peaksZeCopy = np.array(peaksZe)
    
    peaksTbd = list()
    
    for pp,peakStart in enumerate(peaksStartIndices):
      deletePeaks = False
      if peakStart == -9999: continue #peak has been deleted
      followingPeaks = (peaksStartIndices>=peakStart) *  (peaksStartIndices < peakStart+(1.5*self.co["widthSpectrum"]))
      if (np.sum(followingPeaks) >= 3):
	#if you have three peaks so close together it is cristal clear:
	deletePeaks = True
      elif (np.sum(followingPeaks) == 2):
	#if you have only two they must be close together
	secondPeak = np.where(followingPeaks)[0][1]
	deletePeaks = (peaksEndIndices[secondPeak] - peakStart < self.co["widthSpectrum"]/2.)
      if deletePeaks == True :

	Indices = np.where(followingPeaks)[0][0:3] #don't consider more than 3! the rest is hopefully caught by next loop!
	smallestZe = Indices[np.argmin(peaksZeCopy[Indices])]
	#inMiddle = Indices[1]
	#thinnest = Indices[np.argmin(peaksEndIndices[Indices]- peaksStartIndices[Indices])]
	
	#delete if two agree:
	#agreement = int(smallestZe == inMiddle)+int(inMiddle==thinnest)+int(smallestZe==thinnest)
	#if agreement>=1:
	    #if self.co["debug"]>2: print "deleted peak at, no: ",t,pp
	  #if smallestZe==inMiddle:
	peaksTbd.append(smallestZe)
	  #else:
	    #peakTbd = inMiddle
	    #import pdb;pdb.set_trace()
	    #remove them

	#these are needed for the loop, so they are only masked, not deleted
	peaksStartIndices[peaksTbd[-1]]=-9999
	peaksEndIndices[peaksTbd[-1]] = -9999
	peaksZeCopy[peaksTbd[-1]] = 9999
	    
    return peaksTbd

  def  _getTrustedPeak(self,allPeaksZe,allPeaksVelMe,allPeaksRefV,allPeaksMaxIndices,allPeaksHeight):
    '''
    find heigth and position of most trustfull peak
    
    allPeaksZe - time dictonary with lists of first guess Ze for each peak
    allPeaksVelMe - first guess peak velocity based on the last bin
    allPeaksRefV - expected velocity of each peak based on Ze according to theory
    allPeaksMaxIndices - time dictonary maximum of each peak
    allPeaksHeight - first guess peak height based on the last bin
    
    returns 1D time  arrays
    trustedPeakNo - no of trusted peaks (starting at bottom)
    trustedPeakHeight - estimated height
    trustedPeakVel - -estimated velocity
    trustedPeakHeightStart, trustedPeakHeightStop - start and stop indices from 0:192 range
    '''
    trustedPeakHeight = np.zeros(self.no_t,dtype=int)
    trustedPeakVel = np.zeros(self.no_t)
    trustedPeakNo = np.ones(self.no_t,dtype=int)*-9999
    trustedPeakHeightStart = np.zeros(self.no_t)
    trustedPeakHeightStop = np.zeros(self.no_t)
    for t in np.arange(self.no_t):
      #now process the found peaks
      if t in self._allPeaks.keys():
	
	#the trusted peak needs a certain minimal reflectivity to avoid confusion by interference etc, get the minimum threshold
	averageZe = np.sum(allPeaksZe[t])/float(len(allPeaksZe[t]))
	minZe = IMProTooTools.quantile(self._allPeaksZe[t], self.co['dealiaseSpectrum_trustedPeakminZeQuantile'])
	
	
	peaksVelMe = np.array(allPeaksVelMe[t])
	peaksVels = np.array([peaksVelMe+self.co["nyqVdelta"]*self.co["widthSpectrum"],peaksVelMe,peaksVelMe-self.co["nyqVdelta"]*self.co["widthSpectrum"]])
	refVels = np.array([allPeaksRefV[t],allPeaksRefV[t],allPeaksRefV[t]])
	#this difference between real velocity (thee different ones are tried: dealaisisnmg up, static or down) and expected Ze based velocityhas to be minimum to find trusted peak
	diffs = np.abs(peaksVels - refVels)

	#mask small peaks, peaks which are in the firt processed range gate and peaks which are in self.co["dealiaseSpectrum_heightsWithInterference"] (e.g. disturbed by interference)
	diffs = np.ma.masked_array(diffs,[allPeaksZe[t]<=minZe]*3)
	tripplePeaksMaxIndices = np.array(3*[allPeaksMaxIndices[t]])
	#the first used height is a bit special, often peaks are incomplete,try to catch them to avoid trust them
	diffs = np.ma.masked_array(diffs,(tripplePeaksMaxIndices >= self.co["firstUsedHeight"]*self.co["widthSpectrum"])*(tripplePeaksMaxIndices < self.co["firstUsedHeight"]*(self.co["widthSpectrum"]*1.5)))
	#now mask all other peaks which are found unlikely
	for hh in self.co["dealiaseSpectrum_heightsWithInterference"]+self.co["completelyMaskedHeights"]:
	  diffs = np.ma.masked_array(diffs,(tripplePeaksMaxIndices >= hh*self.co["widthSpectrum"])*(tripplePeaksMaxIndices < (hh+1)*self.co["widthSpectrum"]))
	
	#if we managed to mask all peaks, we have no choice but taking all
	if np.all(diffs.mask==True):
	  diffs.mask[:] = False
	  if self.co["debug"]>4 : print "managed to mask all peaks at "+ str(t) +" while trying to find most trustfull one during dealiasing."
	  
	#the minimum velocity difference tells wehther dealiasing goes up, down or is not applied  
	UpOrDn = np.ma.argmin(np.ma.min(diffs,axis=1))
	#get paramters for trusted peaks
	trustedPeakNo[t] = np.ma.argmin(diffs[UpOrDn])
	trustedPeakHeight[t] = allPeaksHeight[t][trustedPeakNo[t]] + UpOrDn-1 # -1 to ensure that updraft is negative now!!
	trustedPeakSpecShift = trustedPeakHeight[t]*self.co["widthSpectrum"] - self.co["widthSpectrum"]
	trustedPeakVel[t] = peaksVels[UpOrDn][trustedPeakNo[t]]
							      #transform back to height related spectrum
	#in dimension of 0:192								#spectrum is extended to the left
	trustedPeakHeightIndices= (np.array(self._allPeaksIndices[t][trustedPeakNo[t]])-trustedPeakSpecShift)[[0,-1]]
	trustedPeakHeightStart[t] = trustedPeakHeightIndices[0]
	trustedPeakHeightStop[t]  = trustedPeakHeightIndices[-1]	  
	
    return trustedPeakNo, trustedPeakHeight, trustedPeakVel, trustedPeakHeightStart, trustedPeakHeightStop

  def _findHeightsForPeaks(self,extendedRawSpectrum,trustedPeakNo,trustedPeakVel,trustedPeakHeight,trustedPeakHeightStart,trustedPeakHeightStop,allPeaks, allPeaksIndices, allPeaksVelMe, allPeaksHeight):
    '''
    try to find the height of each peak by starting at the trusted peak
    extendedRawSpectrum - extended to 192 bins, returned with new, dealiased mask
    trustedPeakNo - trusted peak number of all peaks in time step
    trustedPeakVel - most liekely velocity
    trustedPeakHeight - most likely height
    trustedPeakHeightStart, trustedPeakHeightStop - start/stop of peaks
    allPeaks - time dictonary with lists of the spectral reflectivities for each peak
    allPeaksIndices - related indices
    allPeaksVelMe - first guess peak velocity based on the last bin
    allPeaksHeight - first guess peak height based on the last bin
    '''
    for t in np.arange(self.no_t):
      if t in self._allPeaks.keys():
	extendedRawSpectrum[t,trustedPeakHeight[t], trustedPeakHeightStart[t]:trustedPeakHeightStop[t]+1].mask = False
	
	
	peaksVelMe = np.array(allPeaksVelMe[t])
	#get all three possible velocities
	peaksVels = np.array([peaksVelMe+self.co["nyqVdelta"]*self.co["widthSpectrum"],peaksVelMe,peaksVelMe-self.co["nyqVdelta"]*self.co["widthSpectrum"]])
	
	formerPeakVel = trustedPeakVel[t]
	#loop through all peaks, starting at the trusted one
	for jj in range(trustedPeakNo[t]-1,-1,-1)+range(trustedPeakNo[t]+1,len(allPeaks[t])):
	  #To combine ascending and descending loop in one:
	  if jj == trustedPeakNo[t]+1: formerPeakVel = trustedPeakVel[t]
	  #go up, stay or down? for which option fifference to former (trusted) peaks is smallest.
	  UpOrDn = np.argmin(np.abs(peaksVels[:,jj] - formerPeakVel))
	  #change height, indices and velocity accordingly
	  thisPeakHeight = allPeaksHeight[t][jj] + UpOrDn-1
	  thisPeakSpecShift = thisPeakHeight*self.co["widthSpectrum"] - self.co["widthSpectrum"]
	  thisPeakVel = peaksVels[UpOrDn][jj]
	  thisPeakHeightIndices = np.array(allPeaksIndices[t][jj])-thisPeakSpecShift
	  if np.any(thisPeakHeightIndices<0) or np.any(thisPeakHeightIndices>=3*self.co["widthSpectrum"]):
	    warnings.warn('Dealiasing failed! peak boundaries fall out of spectrum. time step '+str(t)+', peak number '+ str(jj)+', most likely at height '+ str(thisPeakHeight))
	    self.qual["severeProblemsDuringDA"][t] = True
	    
	  #check whether there is already a peak in the found height!
	  if np.all(extendedRawSpectrum[t,thisPeakHeight].mask==True):
	    if thisPeakHeight>= self.co["noH"] or thisPeakHeight<0:
	      warnings.warn('Dealiasing reached max/min height... time step '+str(t)+', peak number '+ str(jj)+', most likely at height '+ str(thisPeakHeight))
	      self.qual["severeProblemsDuringDA"][t] = True
	      continue
	    #only if there is no peak yet!!
	    extendedRawSpectrum[t,thisPeakHeight,thisPeakHeightIndices[0]:thisPeakHeightIndices[-1]+1].mask = False
	    formerPeakVel = thisPeakVel
	  #if there is already a peak in the height, repeat the process, but take the second likely height/velocity
	  else:
	    if self.co["debug"]>4: print 'DA: there is already a peak in found height, take second choice', t,jj,thisPeakHeight,trustedPeakNo[t],trustedPeakHeight
	    #otherwise take second choice!
	    formerPeakVelList = np.array([formerPeakVel]*3)
	    formerPeakVelList[UpOrDn] = 1e10 #make extremely big
	    UpOrDn2 = np.ma.argmin(np.abs(peaksVels[:,jj] - formerPeakVelList))
	    thisPeakHeight = allPeaksHeight[t][jj] + UpOrDn2-1
	    thisPeakSpecShift = thisPeakHeight*self.co["widthSpectrum"] - self.co["widthSpectrum"]
	    thisPeakVel = peaksVels[UpOrDn2][jj]
	    thisPeakHeightIndices = np.array(allPeaksIndices[t][jj])-thisPeakSpecShift
	    if np.any(thisPeakHeightIndices<0) or np.any(thisPeakHeightIndices>=3*self.co["widthSpectrum"]):
	      warnings.warn('Dealiasing step 2 failed! peak boundaries fall out of spectrum. time step '+str(t)+', peak number '+ str(jj)+', most likely at height '+ str(thisPeakHeight))
	      self.qual["severeProblemsDuringDA"][t] = True
	    if thisPeakHeight>= self.co["noH"] or thisPeakHeight<0:
	      warnings.warn('Dealiasing reached max/min height... time step '+str(t)+', peak number '+ str(jj)+', most likely at height '+ str(thisPeakHeight))
	      self.qual["severeProblemsDuringDA"][t] = True
	      continue
	    #check again whether there is already a peak in the spectrum
	    if np.all(extendedRawSpectrum[t,thisPeakHeight].mask==True):
	      #next try
	      extendedRawSpectrum[t,thisPeakHeight,thisPeakHeightIndices[0]:thisPeakHeightIndices[-1]+1].mask = False
	      formerPeakVel = thisPeakVel
	    #if yes, give up
	    else:
	      warnings.warn('Could not find height of peak! time step '+str(t)+', peak number '+ str(jj)+', most likely at height '+ str(thisPeakHeight))   
	      self.qual["severeProblemsDuringDA"][t] = True
    
    return extendedRawSpectrum
    
  def _dealiaseSpectrumAdvanced_OLD_TBD(self,newSpectrum,shiftedSpecIndex,qualityArray,foldingCandidates):
    '''
    #newSpectrum = deepcopy(rawSpectrum)
    #newVelocities = deepcopy(specVel)
    
    #get according velocities
    '''
    shiftedIndices = np.arange(0,self.co["widthSpectrum"]*3)
    checkForDealaiasing = np.where(np.sum(foldingCandidates,axis=-1)>=1)[0]

    foldDirection = np.zeros(np.shape(foldingCandidates),dtype=int)

    noSpecHalf = self.co["widthSpectrum"] / 2
    
    for t in checkForDealaiasing:
      #get all spectra from one time step
      singleSpectrum = deepcopy(newSpectrum[t])
      #don't do anything if everything is masked!'
      if np.all(singleSpectrum.mask == True): 
	if self.co["debug"] > 1: print t, "all masked"
	continue
      if self.co["debug"] > 0: print t
      #find all maxima in the spectrum
      iMax = np.ma.masked_array(np.argmax(singleSpectrum,axis=1),np.all(singleSpectrum.mask,axis=-1))
      #decide which is the most trustfull one, the one closest to rangegate x
      trustfullHeight = np.ma.argmin(np.abs(iMax-20))
      #get the shifted index of the max of the trusted height
      lastMax = iMax[trustfullHeight]+self.co["widthSpectrum"]
      for h in range(trustfullHeight,self.co["noH"]-1):
	#add lower and upper spectra, according velocities can be found in threeVelocities
	threeSpectra = np.ma.concatenate((singleSpectrum[h-1],singleSpectrum[h],singleSpectrum[h+1],))
	# find the most likely peak of the 3 spectra on the basis of the height before
	# don't do anything if there is no peak
	if np.all(threeSpectra.mask[lastMax-noSpecHalf:lastMax+noSpecHalf] == True):
	  if self.co["debug"] > 1: print t,h,"np.all(threeSpectra.mask[lastMax-noSpecHalf:lastMax+noSpecHalf] == True)"
	  newSpectrum[t,h].mask = True
	  #self.co["debug"] obnly: newSpectrum[t,h].mask = np.logical_not(newSpectrum[t,h].mask)
	  continue
	#get borders and width of the most likely peak
	peakMinIndex = np.ma.min(np.where(threeSpectra[lastMax-noSpecHalf:lastMax+noSpecHalf])) + lastMax - noSpecHalf
	peakMaxIndex = np.ma.max(np.where(threeSpectra[lastMax-noSpecHalf:lastMax+noSpecHalf])) + lastMax - noSpecHalf
	peakWidth = peakMaxIndex - peakMinIndex
	#how much spectrum do we have to add to the left and to the right?
	addLeft = (self.co["widthSpectrum"]-peakWidth)/2
	addRight = (self.co["widthSpectrum"]-peakWidth)/2
	if (peakWidth % 2 == 1) : addRight +=1
	#find the new borders, equaly around the peak
	leftBorder = peakMinIndex-addLeft
	rightBorder = peakMaxIndex+addRight
	#what if borders larger than spectrum?
	if leftBorder < 0:
	  leftBorder = 0
	  rightBorder = self.co["widthSpectrum"]
	elif rightBorder > 3*self.co["widthSpectrum"]:
	  leftBorder = 2*self.co["widthSpectrum"]
	  rightBorder = 3*self.co["widthSpectrum"]
	#finally get the new spectrum and the according velocities!
	newSpectrum[t,h] = threeSpectra[leftBorder:rightBorder]
	shiftedSpecIndex[t,h] = shiftedIndices[leftBorder:rightBorder]

	#for statistics, in which direction did we fold
	if leftBorder< self.co["widthSpectrum"]:
	  foldDirection[t,h] = -1
	elif rightBorder >=128:
	  foldDirection[t,h] = 1    
	#and remember the max for the next height
	lastMax = np.argmax(newSpectrum[t,h])+leftBorder
	if self.co["debug"] > 1: print t,h,leftBorder,lastMax
	
      lastMax = iMax[trustfullHeight]+self.co["widthSpectrum"]
      for h in range(trustfullHeight-1,1,-1):
	#if iMax.mask[h] == True:# or foldingCandidates[t,h] == False:
	  #if self.co["debug"] > 1: print t,h,"iMax.mask[h] == True"#" or foldingCandidates[t,h] == False"
	  #continue
	#print t,h
	threeSpectra = np.ma.concatenate((singleSpectrum[h-1],singleSpectrum[h],singleSpectrum[h+1],))
	
	#we don't want a shrinked mask, it has to be full size!
	if threeSpectra.mask.shape == ():
	  threeSpectra.mask = np.ones(threeSpectra.shape,dtype=bool)*threeSpectra.mask
	
	if np.all(threeSpectra.mask[lastMax-noSpecHalf:lastMax+noSpecHalf] == True):
	  if self.co["debug"] > 1: print t,h,"np.all(threeSpectra.mask[lastMax-noSpecHalf:lastMax+noSpecHalf] == True)"
	  #self.co["debug"] only newSpectrum[t,h].mask = np.logical_not(newSpectrum[t,h].mask)
	  newSpectrum[t,h].mask = True
	  continue
	peakMinIndex = np.ma.min(np.where(threeSpectra[lastMax-noSpecHalf:lastMax+noSpecHalf])) + lastMax - noSpecHalf
	peakMaxIndex = np.ma.max(np.where(threeSpectra[lastMax-noSpecHalf:lastMax+noSpecHalf])) + lastMax - noSpecHalf
	peakWidth = peakMaxIndex - peakMinIndex
	addLeft = (self.co["widthSpectrum"]-peakWidth)/2
	addRight = (self.co["widthSpectrum"]-peakWidth)/2
	if (peakWidth % 2 == 1) : addRight +=1
	leftBorder = peakMinIndex-addLeft
	rightBorder = peakMaxIndex+addRight
	if leftBorder < 0:
	  leftBorder = 0
	  rightBorder = self.co["widthSpectrum"]
	elif rightBorder > 3*self.co["widthSpectrum"]:
	  leftBorder = 2*self.co["widthSpectrum"]
	  rightBorder = 3*self.co["widthSpectrum"]
	newSpectrum[t,h] = threeSpectra[leftBorder:rightBorder]
	shiftedSpecIndex[t,h] = shiftedIndices[leftBorder:rightBorder]
	#for statistics, in which direction did we fold
	if leftBorder< self.co["widthSpectrum"]:
	  foldDirection[t,h] = -1
	elif rightBorder >=128:
	  foldDirection[t,h] = 1    
	lastMax = np.argmax(newSpectrum[t,h])+leftBorder
	if self.co["debug"] > 1: print t,h,leftBorder,lastMax

    qualityArray[foldDirection == 1] = qualityArray[foldDirection == 1] +   0b0000000000100000 #11) spectrum dealiased to the right 
    qualityArray[foldDirection == -1] = qualityArray[foldDirection == -1] + 0b0000000001000000 #10) spectrum dealiased to the left 
    
    return newSpectrum,shiftedSpecIndex,qualityArray,foldDirection

  def _deAlCoherence(self,newSpectrum,newShiftedIndex,oldSpectrum,qualityArray,foldDirection,foldingCandidates):
    '''
    make sure no weired foldings happend
    '''
    #checkForWeiredFolding = (np.all(foldDirection>=0,axis=-1) + np.all(foldDirection<=0,axis=-1)) * (np.sum(foldingCandidates,axis=-1)>1)
    checkForWeiredFolding = np.sum(foldingCandidates,axis=-1)>1
    foldDirectionPerTimeStep = [cmp(i,0) for i in np.sum(foldDirection,axis=-1)]
    lastFolding = 0
    #import pdb; pdb.set_trace()
    for t in np.arange(np.shape(oldSpectrum)[0]):
      if self.co["debug"] > 4: print t,checkForWeiredFolding[t],foldDirectionPerTimeStep[t],lastFolding
      if checkForWeiredFolding[t] == False or foldDirectionPerTimeStep[t] == 0:
	lastFolding = 0
	continue
      
      if lastFolding != foldDirectionPerTimeStep[t] and lastFolding!= 0:
	if self.co["debug"] > 1: print "ALERT",t,"crazy fold!",foldDirectionPerTimeStep[t]
	
	#repair here
	#
	if foldDirectionPerTimeStep[t] == 1:
	  iToMove = np.where(foldDirection[t] == 1)[0]
	  newSpectrum[t,iToMove + 1] = newSpectrum[t,iToMove]
	  newSpectrum[t,iToMove[0]] = oldSpectrum[t,iToMove[0]]
	  newShiftedIndex[t,iToMove + 1] = newShiftedIndex[t,iToMove] -  self.co["widthSpectrum"]
	  newShiftedIndex[t,iToMove[0]] = np.arange(self.co["widthSpectrum"]) + self.co["widthSpectrum"]
	  qualityArray[t] = qualityArray[t] + 0b0000000000010000 #12) spectrum refolded due to coherence test!

	  
	elif foldDirectionPerTimeStep[t] == -1:
	  iToMove = np.where(foldDirection[t] == -1)[0]
	  newSpectrum[t,iToMove -1 ] = newSpectrum[t,iToMove]
	  newSpectrum[t,iToMove[-1]] = oldSpectrum[t,iToMove[-1]]
	  newShiftedIndex[t,iToMove -1 ] = newShiftedIndex[t,iToMove] +  self.co["widthSpectrum"]
	  newShiftedIndex[t,iToMove[-1]] = np.arange(self.co["widthSpectrum"]) + self.co["widthSpectrum"]
	  self.quality[t] = qualityArray[t] + 0b0000000000010000 #12) spectrum refolded due to coherence test!
	
	
	lastFolding = lastFolding
      else:
	lastFolding = foldDirectionPerTimeStep[t]
	
    return newSpectrum,newShiftedIndex,qualityArray

  def _deAlCoherence2(self,newSpectrum):
    '''
    make sure no weired foldings happend by looking for big jumps in the height-averaged velocity
    if two jumps very closely together (<=3 peaks inbetween) are found, teh peaks inbetween are corrected
    can make it worse if dealiasing produces zig-zag patterns.
    
    '''
    
    self.qual["DAdirectionCorrectedByCoherenceTest"] = np.zeros(self._shape2D)
    meanVelocity = np.ma.average(np.ma.sum(newSpectrum*self.specVel,axis=-1)/np.ma.sum(newSpectrum,axis=-1),axis=-1)
  
    velDiffs = np.diff(meanVelocity)
        
    velDiffsBig = np.where(velDiffs > self.co["dealiaseSpectrum_makeCoherenceTest_velocityThreshold"])[0]
    velDiffsSmall = np.where(velDiffs < -self.co["dealiaseSpectrum_makeCoherenceTest_velocityThreshold"])[0]
   
    foldUp = list()
    
    for ll in  velDiffsBig:
      if ll+1 in velDiffsSmall:
	foldUp.append(ll+1)
	continue
      if ll+2 in velDiffsSmall:
	foldUp.append(ll+1)
	foldUp.append(ll+2)
	continue
      if ll+3 in velDiffsSmall:
	foldUp.append(ll+1)
	foldUp.append(ll+2)
	foldUp.append(ll+3)
 
    #import pdb;pdb.set_trace()  
    updatedSpectrumMask = deepcopy(newSpectrum.mask)
  
    for tt in foldUp:
      updatedSpectrumMask[tt] = np.roll(updatedSpectrumMask[tt].ravel(),2* self.co["widthSpectrum"]).reshape((self.co["noH"],3*self.co["widthSpectrum"]))
      #updatedSpectrumMask[tt,-1,-self.co["widthSpectrum"]:] = True
      self.qual["DAdirectionCorrectedByCoherenceTest"][tt,:] = True
    if self.co["debug"] > 4: print 'coherenceTest corrected dealiasing upwards:', foldUp

    newSpectrum = np.ma.masked_array(newSpectrum.data,updatedSpectrumMask)

    #now the same for the other folding direction
    meanVelocity = np.ma.average(np.ma.sum(newSpectrum*self.specVel,axis=-1)/np.ma.sum(newSpectrum,axis=-1),axis=-1)
  
    velDiffs = np.diff(meanVelocity)

    #find very big differences
    velDiffsBig = np.where(velDiffs > self.co["dealiaseSpectrum_makeCoherenceTest_velocityThreshold"])[0]
    velDiffsSmall = np.where(velDiffs < -self.co["dealiaseSpectrum_makeCoherenceTest_velocityThreshold"])[0]
    
    foldDn = list()
    #check whether there is an opposite one close by and collect time steps to be refolded
    for ll in  velDiffsSmall:
      if ll+1 in velDiffsBig:
	foldDn.append(ll+1)
	continue
      if ll+2 in velDiffsBig:
	foldDn.append(ll+1)
	foldDn.append(ll+2)
	continue
      if ll+3 in velDiffsBig:
	foldDn.append(ll+1)
	foldDn.append(ll+2)
	foldDn.append(ll+2)
 
    #import pdb;pdb.set_trace()  
	
    updatedSpectrumMask = deepcopy(newSpectrum.mask)
    #change all peaks accordingly
    for tt in foldDn:
      #roll the mask!
      updatedSpectrumMask[tt] = np.roll(updatedSpectrumMask[tt].ravel(),-2*self.co["widthSpectrum"]).reshape((self.co["noH"],3*self.co["widthSpectrum"]))
      #avoid that something is folded into the lowest range gate
      updatedSpectrumMask[tt,0,:self.co["widthSpectrum"]] = True
      self.qual["DAdirectionCorrectedByCoherenceTest"][tt,:] = True
    if self.co["debug"] > 4: print 'coherenceTest corrected dealiasing Donwards:', foldDn

    newSpectrum = np.ma.masked_array(newSpectrum.data,updatedSpectrumMask)
    
    
    #this method is very incompelte, so save still odd looking peaks in the quality mask:
    #first, collect all height which should be treated, we don't want to find jumps of the interpolated area!: 
    includedHeights = list(set(range(self.co["maxH"])).difference(set(self.co["completelyMaskedHeights"]+self.co["dealiaseSpectrum_heightsWithInterference"])))
    #now get the mean velocity of the profile
    meanVelocity = np.ma.average(np.ma.sum(newSpectrum[:,includedHeights]*self.specVel,axis=-1)/np.ma.sum(newSpectrum[:,includedHeights],axis=-1),axis=-1)
    velDiffs = np.abs(np.diff(meanVelocity))
    #find all steps exceeding a min velocity threshold
    crazyVelDiffs = np.where(velDiffs > self.co["dealiaseSpectrum_makeCoherenceTest_velocityThreshold"])[0]
    
    self.qual["DAbigVelocityJumpDespiteCoherenceTest"] = np.zeros(self._shape2D,dtype=bool)
    #surrounding data has to be masked as well, take +- self.co["dealiaseSpectrum_makeCoherenceTest_maskRadius"] (default 20min) around suspicous data
    for crazyVelDiff in crazyVelDiffs:
      self.qual["DAbigVelocityJumpDespiteCoherenceTest"][crazyVelDiff-self.co["dealiaseSpectrum_makeCoherenceTest_maskRadius"]:crazyVelDiff+self.co["dealiaseSpectrum_makeCoherenceTest_maskRadius"]+1,:] = True  
      
           
      
    return newSpectrum
    
  def _oneD2twoD(self,vector,shape2,axis):
    if axis == 0:
      matrix = np.zeros((shape2,len(vector)))
      for h in np.arange(shape2):
	matrix[h]= vector
    elif axis == 1:
      matrix = np.zeros((len(vector),shape2))
      for h in np.arange(shape2):
	matrix[:,h]= vector
    else:
      raise ValueError("wrong axis")
    return matrix
  
  def _calcEtaZeW(self,rawSpectra,heights,velocities,noise):
    '''
    '''

    deltaH = self._oneD2twoD(heights[...,15]-heights[...,14], heights.shape[-1], 1)
    
    #transponieren um multiplizieren zu ermoeglichen!
    eta = (rawSpectra.data.T * np.array((self.co["mrrCalibConst"] * (heights**2 / deltaH)) / ( 1e20),dtype=float).T).T
    eta = np.ma.masked_array(eta,rawSpectra.mask)
        
    #calculate Ze
    Ze  = 1e18*(self.co["lamb"]**4*np.ma.sum(eta,axis=-1)/(np.pi**5*self.co["K2"]))
    Ze = (10*np.ma.log10(Ze)).filled(-9999)
    Znoise  = 1e18*(self.co["lamb"]**4*(noise*self.co["widthSpectrum"])/(np.pi**5*self.co["K2"]))
    Znoise = 10*np.ma.log10(Znoise)
    #no slicing neccesary due to mask!
    W = np.ma.sum(velocities*rawSpectra,axis=-1) / np.ma.sum(rawSpectra,axis=-1)
    W = W.filled(-9999)
    specWidth = np.ma.abs(np.ma.sum(rawSpectra*(velocities.T-W.T).T**2,axis=-1) / np.ma.sum(rawSpectra,axis=-1)).filled(-9999)
    
    peakLeftBorder = self.specVel[np.argmin(rawSpectra.mask,axis=-1)]
    peakRightBorder = self.specVel[len(self.specVel) - np.argmin(rawSpectra.mask[...,::-1],axis=-1) - 1]
    peakLeftBorder[Ze == -9999] = -9999
    peakRightBorder[Ze == -9999] = -9999
    return eta, Ze, W, Znoise, specWidth, peakLeftBorder, peakRightBorder
    
    
  def getQualityBinArray(self,qual):
    
    binQual = np.zeros(self._shape2D,dtype=int)
    qualFac=dict()
    description = ''
    description += 'usually these ones can be ignored: '
    qualFac["interpolatedSpectrum"] 			= 0b1
    description += '1) spectrum interpolated around 0 and 12 m/s '
    qualFac["filledInterpolatedPeakGaps"] 		= 0b10
    description += '2) peak streches over interpolated part '
    qualFac["spectrumIsDealiased"] 			= 0b100
    description += '3) peak is dealiased '
    qualFac["usedSecondPeakAlgorithmDueToWidePeak"]	= 0b1000
    description += '4) first Algorithm to determine peak failed, used backup '
    qualFac["DAdirectionCorrectedByCoherenceTest"]	= 0b10000
    description += '5) dealiasing went wrong, but is corrected '
    
    description += 'reasons why a spectrum does NOT contain a peak: '
    qualFac["incompleteSpectrum"]			= 0b10000000
    description += '8) spectrum was incompletely recorded '
    qualFac["spectrumVarianceTooLowForPeak"]		= 0b100000000
    description += '9) the variance test indicated no peak '
    qualFac["spectrumNotProcessed"]			= 0b1000000000
    description += '10) spectrum is not processed due to according setting '
    qualFac["peakTooThinn"]				= 0b10000000000
    description += '11) peak removed since not wide enough '
    qualFac["peakRemovedByCoherenceTest"]		= 0b100000000000
    description += '12) peak removed, because too few neighbours show signal, too '
    qualFac["peakRemovedBySnrTest"]			= 0b1000000000000
    description += '13) peak removed because of low SNR '
    
    description += "thinks went seriously wrong, don't use this data "
    qualFac["peakMightBeIncomplete"]			= 0b1000000000000000
    description += '16) peak is at the very border to bad data '
    qualFac["DAbigVelocityJumpDespiteCoherenceTest"]	= 0b10000000000000000 
    description += '17) in this area there are still strong velocity jumps, indicates failed dealiasing '
    qualFac["severeProblemsDuringDA"]			= 0b100000000000000000
    description += '18) during dealiasing, a warning was triggered, applied to whole columm '

    for key in qual.keys():
      binQual[:] = binQual[:] + (qual[key] * qualFac[key])

    return binQual, description
    
    
    
    
  def writeNetCDF(self,fname,varsToSave="all",ncForm="NETCDF3"):
    '''
    write the results to a netcdf file
    
    Input:
    
    fname: str filename with path
    varsToSave list of variables of the profile to be saved. "all" saves all implmented ones
    ncForm: str netcdf file format, possible values are NETCDF3_CLASSIC, NETCDF3_64BIT, NETCDF4_CLASSIC, and NETCDF4 for the python-netcdf4 package (NETCDF3_CLASSIC gives netcdf4 files for newer ubuntu versions!!\) NETCDF3 takes the "old" Scientific.IO.NetCDF module, which is a bit more convinient
    '''
    
    #most syntax is identical, but there is one nasty difference regarding the fillValue...
    if ncForm in ["NETCDF3_CLASSIC", "NETCDF3_64BIT", "NETCDF4_CLASSIC", "NETCDF4"]:
	    import netCDF4 as nc
	    pyNc = True
    elif ncForm in ["NETCDF3"]:
	    try:
		    import Scientific.IO.NetCDF as nc
		    pyNc = False
	    except:
		    #fallback for cheops cluster with the same syntax as netcdf4!
		    import netCDF3 as nc
		    pyNc = True
    else:
	    raise ValueError("Unknown nc form "+ncForm)
      
    if pyNc: cdfFile = nc.Dataset(fname,"w",ncForm)
    else: cdfFile = nc.NetCDFFile(fname,"w")
    
    #write meta data
    cdfFile.history = "Created with IMProToo by "+self.co["ncCreator"]+" at "+ datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    cdfFile.description = self.co["ncDescription"]    
    cdfFile.author = self.co["ncCreator"]
    cdfFile.properties = str(self.co)
    cdfFile.mrrHeader = str(self.header)
    
    #make frequsnions
    cdfFile.createDimension('time',int(self.no_t))
    cdfFile.createDimension('range',int(self.no_h))
    cdfFile.createDimension('velocity',int(self.no_v))
    if self.co["dealiaseSpectrum_saveAlsoNonDealiased"]: cdfFile.createDimension('velocity_noDA',int(self.no_v_noDA))
    
    ncShape2D = ("time","range",)
    ncShape3D = ("time","range","velocity",)
    ncShape3D_noDA = ("time","range","velocity_noDA",)
    
    fillVDict = dict()
    #little cheat to avoid hundreds of if, else...
    if pyNc: fillVDict["fill_value"] = missingNumber
    
    nc_time = cdfFile.createVariable('time','i',('time',),**fillVDict)
    nc_time.units = 'seconds since 1970-01-01'
    nc_time[:] = np.array(self.time.filled(self.missingNumber),dtype="i4")
    if not pyNc: nc_time._FillValue =int(self.missingNumber)
  
    nc_range = cdfFile.createVariable('range','i',('range',),**fillVDict)#= missingNumber)
    nc_range.units = '#'
    nc_range[:] = np.arange(self.co["minH"],self.co["maxH"]+1,dtype="i4")
    if not pyNc: nc_range._FillValue =int(self.missingNumber)
    
    nc_velocity = cdfFile.createVariable('velocity','f',('velocity',),**fillVDict)
    nc_velocity.units = 'm/s'
    nc_velocity[:] = np.array(self.specVel,dtype="f4")
    if not pyNc: nc_velocity._FillValue =float(self.missingNumber)
    
    if self.co["dealiaseSpectrum_saveAlsoNonDealiased"]: 
      nc_velocity_noDA = cdfFile.createVariable('velocity_noDA','f',('velocity_noDA',),**fillVDict)
      nc_velocity_noDA.units = 'm/s'
      nc_velocity_noDA[:] = np.array(self.specVel_noDA,dtype="f4")
      if not pyNc: nc_velocity_noDA._FillValue =float(self.missingNumber)

    
    nc_height = cdfFile.createVariable('height','f',ncShape2D,**fillVDict)#= missingNumber)
    nc_height.units = 'm'
    nc_height[:] = np.array(self.H.filled(self.missingNumber),dtype="f4")
    if not pyNc: nc_height._FillValue =float(self.missingNumber)
    
    if varsToSave=='all' or "eta_noDA" in varsToSave:
      nc_eta_noDA = cdfFile.createVariable('eta_noDA', 'f',ncShape3D_noDA,**fillVDict)
      nc_eta_noDA.units = "1/m"
      nc_eta_noDA[:] = np.array(self.eta_noDA.data,dtype="f4")
      if not pyNc: nc_eta_noDA._FillValue =float(self.missingNumber)

      nc_etaMask_noDA = cdfFile.createVariable('etaMask_noDA', 'i',ncShape3D_noDA,**fillVDict)
      nc_etaMask_noDA.description = "0: signal, 1:noise"
      nc_etaMask_noDA.units = "bool"
      nc_etaMask_noDA[:] = np.array(np.array(self.eta_noDA.mask,dtype=int),dtype="i4")
      if not pyNc: nc_etaMask_noDA._FillValue =int(self.missingNumber)

    if varsToSave=='all' or "eta" in varsToSave:
      nc_eta = cdfFile.createVariable('eta', 'f',ncShape3D,**fillVDict)
      nc_eta.units = "1/m"
      nc_eta[:] = np.array(self.eta.data,dtype="f4")
      if not pyNc: nc_eta._FillValue =float(self.missingNumber)

      nc_etaMask = cdfFile.createVariable('etaMask', 'i',ncShape3D,**fillVDict)
      nc_etaMask.description = "0: signal, 1:noise"
      nc_etaMask.units = "bool"
      nc_etaMask[:] = np.array(np.array(self.eta.mask,dtype=int),dtype="i4")
      if not pyNc: nc_etaMask._FillValue =int(self.missingNumber)

    if varsToSave=='all' or "quality" in varsToSave:
      qualArray, qualDescription = self.getQualityBinArray(self.qual)
      
      nc_qual = cdfFile.createVariable('quality', 'i',ncShape2D,**fillVDict)
      nc_qual.description = qualDescription
      nc_qual.units = "bin"
      nc_qual[:] = np.array(qualArray,dtype="i4")
      if not pyNc: nc_qual._FillValue =int(self.missingNumber)

     
    if varsToSave=='all' or "TF" in varsToSave:
      nc_TF = cdfFile.createVariable('TF', 'f',ncShape2D,**fillVDict)
      nc_TF.units = "-"
      nc_TF[:] = np.array(self.TF.filled(self.missingNumber),dtype="f4")
      if not pyNc: nc_TF._FillValue =float(self.missingNumber)

    if varsToSave=='all' or "Ze_noDA" in varsToSave:
      nc_ze_noDA = cdfFile.createVariable('Ze_noDA', 'f',ncShape2D,**fillVDict)
      nc_ze_noDA.units = "dBz"
      nc_ze_noDA[:] = np.array(self.Ze_noDA,dtype="f4")
      if not pyNc: nc_ze_noDA._FillValue =float(self.missingNumber)
      
    if varsToSave=='all' or "Ze" in varsToSave:
      nc_ze = cdfFile.createVariable('Ze', 'f',ncShape2D,**fillVDict)
      nc_ze.units = "dBz"
      nc_ze[:] = np.array(self.Ze,dtype="f4")
      if not pyNc: nc_ze._FillValue =float(self.missingNumber)

    if varsToSave=='all' or "specWidth_noDA" in varsToSave:
      nc_specWidth_noDA = cdfFile.createVariable('spectralWidth_noDA', 'f',ncShape2D,**fillVDict)
      nc_specWidth_noDA.units = "m^2/s^2"
      nc_specWidth_noDA[:] = np.array(self.specWidth_noDA,dtype="f4")
      if not pyNc: nc_specWidth_noDA._FillValue =float(self.missingNumber)
      
    if varsToSave=='all' or "specWidth" in varsToSave:
      nc_specWidth = cdfFile.createVariable('spectralWidth', 'f',ncShape2D,**fillVDict)
      nc_specWidth.units = "m^2/s^2"
      nc_specWidth[:] = np.array(self.specWidth,dtype="f4")
      if not pyNc: nc_specWidth._FillValue =float(self.missingNumber)

    if varsToSave=='all' or "peakLeftBorder_noDA" in varsToSave:
      nc_peakLeftBorder_noDA = cdfFile.createVariable('peakLeftBorder_noDA', 'f',ncShape2D,**fillVDict)
      nc_peakLeftBorder_noDA.units = "m/s"
      nc_peakLeftBorder_noDA[:] = np.array(self.peakLeftBorder_noDA,dtype="f4")
      if not pyNc: nc_peakLeftBorder_noDA._FillValue =float(self.missingNumber)
      
    if varsToSave=='all' or "peakLeftBorder" in varsToSave:
      nc_peakLeftBorder = cdfFile.createVariable('peakLeftBorder', 'f',ncShape2D,**fillVDict)
      nc_peakLeftBorder.units = "m/s"
      nc_peakLeftBorder[:] = np.array(self.peakLeftBorder,dtype="f4")
      if not pyNc: nc_peakLeftBorder._FillValue =float(self.missingNumber)

    if varsToSave=='all' or "peakRightBorder_noDA" in varsToSave:
      nc_peakRightBorder_noDA = cdfFile.createVariable('peakRightBorder_noDA', 'f',ncShape2D,**fillVDict)
      nc_peakRightBorder_noDA.units = "m/s"
      nc_peakRightBorder_noDA[:] = np.array(self.peakRightBorder_noDA,dtype="f4")
      if not pyNc: nc_peakRightBorder_noDA._FillValue =float(self.missingNumber)
      
    if varsToSave=='all' or "peakRightBorder" in varsToSave:
      nc_peakRightBorder = cdfFile.createVariable('peakRightBorder', 'f',ncShape2D,**fillVDict)
      nc_peakRightBorder.units = "m/s"
      nc_peakRightBorder[:] = np.array(self.peakRightBorder,dtype="f4")
      if not pyNc: nc_peakRightBorder._FillValue =float(self.missingNumber)

    if varsToSave=='all' or "W_noDA" in varsToSave:
      nc_w_noDA = cdfFile.createVariable('W_noDA', 'f',ncShape2D,**fillVDict)
      nc_w_noDA.units = "m/s"
      nc_w_noDA[:] = np.array(self.W_noDA,dtype="f4")
      if not pyNc: nc_w_noDA._FillValue =float(self.missingNumber)
      
    if varsToSave=='all' or "W" in varsToSave:
      nc_w = cdfFile.createVariable('W', 'f',ncShape2D,**fillVDict)
      nc_w.units = "m/s"
      nc_w[:] = np.array(self.W,dtype="f4")
      if not pyNc: nc_w._FillValue =float(self.missingNumber)
      
    if varsToSave=='all' or "Noise_noDA" in varsToSave:
      nc_noise_noDA = cdfFile.createVariable('Noise_noDA', 'f',ncShape2D,**fillVDict)
      nc_noise_noDA.units = "dB"
      nc_noise_noDA[:] = np.array(self.Znoise_noDA,dtype="f4")
      if not pyNc: nc_noise_noDA._FillValue =float(self.missingNumber)

    if varsToSave=='all' or "Noise" in varsToSave:
      nc_noise = cdfFile.createVariable('Noise', 'f',ncShape2D,**fillVDict)
      nc_noise.units = "dB"
      nc_noise[:] = np.array(self.Znoise,dtype="f4")
      if not pyNc: nc_noise._FillValue =float(self.missingNumber)
          
    cdfFile.close()
    return
    





class mrrProcessedData:
  '''
  Class to read and process MRR average or instantaneous data
  '''
  missingNumber = -9999
  
  def __init__(self,fname,debugLimit = 0,maskData=True):
    """
    reads MRR Average or Instantaneous data. The data is not converted, no magic! The input files can be .gz compressed. Invalid or missing data is marked as nan

    @parameter fname (str): Filename, wildcards allowed!
    @parameter debugLimit (int): stop after debugLimit timestamps

    No return, but provides MRR dataset variables 
    """
    #some helper functions!
    def splitMrrAveData(string,debugTime,floatInt):
      '''
      splits one line of mrr data into list
      @parameter string (str) string of MRR data
      @parameter debugTime (int) time for debug output
      @parameter floatInt (type) convert float or integer
      
      @retrun array with mrr data
      '''
      listOfData = list()
      listOfData_append = listOfData.append
      
      i_start = 3
      i_offset = 7
      try:
        for k in np.arange(i_start,i_offset*31,i_offset):
            listOfData_append(mrrDataEsc(string[k:k+i_offset],floatInt))
      except:
	#try to fix MRR bug
        print "repairing data at " + str(IMProTooTools.unix2date(debugTime))
        string = string.replace("10000.0","10000.")
        string = string.replace("1000.00","1000.0")
        string = string.replace("100.000","100.00")
        string = string.replace("10.0000","10.000")
        string = string.replace("1.00000","1.0000")
        listOfData = list()
        listOfData_append = listOfData.append
        for k in np.arange(i_start,i_offset*31,i_offset):
          try:
            listOfData_append(mrrDataEsc(string[k:k+i_offset],floatInt))
          except:
            print("######### Warning, Corrupt data at "+ str(IMProTooTools.unix2date(debugTime))+ ", position "+str(k)+": " + string+" #########")
            listOfData_append(np.nan)
      return np.array(listOfData)
    
    def mrrDataEsc(string,floatInt):
      """
      set invalid data to nan!
      
      @parameter string (str): string from mrr data
      @parameter floatInt (function): int or float function

      @return - float or int number
      """

      if (string == " "*7) or (len(string)!=7):
        return np.nan
      else:
        return floatInt(string)  

    files = glob.glob(fname)
    files.sort()
    
    foundAtLeastOneFile = False
    
    #go through all files
    for f,file in enumerate(files):
      print "%s of %s:"%(f+1,len(files)), file
      
      #open file, gzip or ascii
      try:
        if file[-3:]==".gz":
          try: allData = gzip.open(file, 'rb')
          except: 
            print "could not open:", file
            raise IOError("could not open:"+ file)
        else:
          try: allData = open(file, 'r')
          except: 
            print "could not open:", file
            raise IOError("could not open:"+ file)
      
        if len(allData.read(10))==0:
          print file, "empty!"
          allData.close()
          raise IOError("File empty")
        else:
          allData.seek(0)
          i=0
      except IOError:
        print "skipping..."
        continue
      
      foundAtLeastOneFile = True
      
      #go through file and make a dictionary with timestamp as key and all corresponding lines of data as values
      dataMRR = {}
      prevDate=0
      tmpList = list()
      for line in allData:
        if line[0:3] == "MRR":
            if i != 0:
              dataMRR[prevDate] = tmpList
            tmpList = []
            asciiDate = line[4:20]
            # We must have UTC!
            if ( re.search("UTC", line) == None):
              sys.exit("Warning, must be UTC!")
            date = datetime.datetime(year = 2000+int(asciiDate[0:2]), month = int(asciiDate[2:4]), day = int(asciiDate[4:6]), hour = int(asciiDate[6:8]), minute = int(asciiDate[8:10]), second = int(asciiDate[10:12]))
            date = int(date2unix(date))
            tmpList.append(line)
            prevDate = date
        else:
            tmpList.append(line)
        i += 1

      dataMRR[prevDate] = tmpList
      allData.close()
      
      try:
        del dataMRR[0]
        print "Warning: some lines without timestamp"
      except:
        pass

      if debugLimit == 0:
        debugLimit = len(dataMRR.keys())
        
      #create arrays for data
      aveTimestamps=  	np.array(np.sort(dataMRR.keys())[0:debugLimit],dtype=int)
      aveH =          	np.ones((debugLimit,31),dtype=float)*np.nan
      aveTF =         	np.ones((debugLimit,31),dtype=float)*np.nan
      aveF =          	np.ones((debugLimit,31,64),dtype=float)*np.nan
      aveN =		np.ones((debugLimit,31,64),dtype=float)*np.nan
      aveD =		np.ones((debugLimit,31,64),dtype=float)*np.nan
      aveK =      	np.ones((debugLimit,31),dtype=float)*np.nan
      aveCapitalZ =     np.ones((debugLimit,31),dtype=float)*np.nan
      aveSmallz =    	np.ones((debugLimit,31),dtype=float)*np.nan
      avePIA =     	np.ones((debugLimit,31),dtype=float)*np.nan
      aveRR =      	np.ones((debugLimit,31),dtype=float)*np.nan
      aveLWC =      	np.ones((debugLimit,31),dtype=float)*np.nan
      aveW =        	np.ones((debugLimit,31),dtype=float)*np.nan
      
      #go through timestamps and fill up arrays
      for t,timestamp in enumerate(aveTimestamps[0:debugLimit]):
        #print unix2date(timestamp)
        dataSet = dataMRR[timestamp]
        for dataLine in dataSet:
          if dataLine[0:3] == "MRR":
            self.header = dataLine[21:-2] # just one is stored, thus no array
            continue #print timestamp
          elif dataLine[0:3] == "H  ":
            aveH[t,:] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif dataLine[0:3] == "TF ":
            aveTF[t,:] = splitMrrAveData(dataLine,timestamp,float)
            continue #print "TF"
          elif dataLine[0:1] == "F":
            try:
              specBin = int(dataLine[1:3])
            except:
              print("######### Warning, Corrupt data header at "+ str(IMProTooTools.unix2date(timestamp))+ ", " + dataLine+" #########")
              continue
            aveF[t,:,specBin] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif dataLine[0:1] == "D":
            try:
              specBin = int(dataLine[1:3])
            except:
              print("######### Warning, Corrupt data header at "+ str(IMProTooTools.unix2date(timestamp))+ ", " + dataLine+" #########")
              continue
            aveD[t,:,specBin] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif dataLine[0:1] == "N":
            try:
              specBin = int(dataLine[1:3])
            except:
              print("######### Warning, Corrupt data header at "+ str(IMProTooTools.unix2date(timestamp))+ ", " + dataLine+" #########")
              continue
            aveN[t,:,specBin] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif dataLine[0:3] == "K  ":
            aveK[t,:] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif dataLine[0:3] == "PIA":
            avePIA[t,:] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif dataLine[0:3] == "Z  ":
            aveCapitalZ[t,:] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif dataLine[0:3] == "z  ":
            aveSmallz[t,:] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif dataLine[0:3] == "RR ":
            aveRR[t,:] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif dataLine[0:3] == "LWC":
            aveLWC[t,:] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif dataLine[0:3] == "W  ":
            aveW[t,:] = splitMrrAveData(dataLine,timestamp,float)
            continue
          elif len(dataLine)==2:
            continue
          else:
            print "? Line not recognized:", str(IMProTooTools.unix2date(timestamp)), dataLine, len(dataLine)
      
      #join arrays of different files
      try:
        self.mrrTimestamps = np.concatenate((self.mrrTimestamps,aveTimestamps),axis=0)
        self.mrrH = np.concatenate((self.mrrH,aveH),axis=0)
        self.mrrTF = np.concatenate((self.mrrTF,aveTF),axis=0)
        self.mrrF = np.concatenate((self.mrrF,aveF),axis=0)
        self.mrrN = np.concatenate((self.mrrN,aveN),axis=0)
        self.mrrD = np.concatenate((self.mrrD,aveD),axis=0)
        self.mrrK = np.concatenate((self.mrrK,aveK),axis=0)
        self.mrrPIA = np.concatenate((self.mrrPIA,avePIA),axis=0)
        self.mrrCapitalZ = np.concatenate((self.mrrCapitalZ,aveCapitalZ),axis=0)
        self.mrrSmallz = np.concatenate((self.mrrSmallz,aveSmallz),axis=0)
        self.mrrRR = np.concatenate((self.mrrRR,aveRR),axis=0)
        self.mrrLWC = np.concatenate((self.mrrLWC,aveLWC),axis=0)
        self.mrrW = np.concatenate((self.mrrW,aveW),axis=0)
      except AttributeError:
        self.mrrTimestamps = aveTimestamps
        self.mrrH = aveH
        self.mrrTF = aveH
        self.mrrF = aveF
        self.mrrN = aveN
        self.mrrD = aveD
        self.mrrK = aveK
        self.mrrPIA = avePIA
        self.mrrCapitalZ = aveCapitalZ
        self.mrrSmallz = aveSmallz
        self.mrrRR = aveRR
        self.mrrLWC = aveLWC
        self.mrrW = aveW
    if foundAtLeastOneFile == False:
      print("NO DATA")
      raise UnboundLocalError
    try: self.header
    except:
      print "did not find any MRR data in file!"
      raise IOError("did not find any MRR data in file!")
    del aveTimestamps,aveH,aveTF,aveF,aveN,aveD,aveK,avePIA,aveCapitalZ,aveSmallz,aveRR,aveLWC,aveW
    
    if maskData:
      self.mrrTimestamps = np.ma.masked_array(self.mrrTimestamps,np.isnan(self.mrrTimestamps))
      self.mrrH = np.ma.masked_array(self.mrrH,np.isnan(self.mrrH))
      self.mrrTF = np.ma.masked_array(self.mrrTF,np.isnan(self.mrrTF))
      self.mrrF = np.ma.masked_array(self.mrrF,np.isnan(self.mrrF))
      self.mrrN = np.ma.masked_array(self.mrrN,np.isnan(self.mrrN))
      self.mrrD = np.ma.masked_array(self.mrrD,np.isnan(self.mrrD))
      self.mrrK = np.ma.masked_array(self.mrrK,np.isnan(self.mrrK))
      self.mrrPIA = np.ma.masked_array(self.mrrPIA,np.isnan(self.mrrPIA))
      self.mrrCapitalZ = np.ma.masked_array(self.mrrCapitalZ,np.isnan(self.mrrCapitalZ))
      self.mrrSmallz = np.ma.masked_array(self.mrrSmallz,np.isnan(self.mrrSmallz))
      self.mrrRR = np.ma.masked_array(self.mrrRR,np.isnan(self.mrrRR))
      self.mrrLWC = np.ma.masked_array(self.mrrLWC,np.isnan(self.mrrLWC))
      self.mrrW = np.ma.masked_array(self.mrrW,np.isnan(self.mrrW))

    self.shape2D = np.shape(self.mrrH)
    self.shape3D = np.shape(self.mrrF)

    print "done reading"
  #end def __init__

  def write2NetCDF(self,fileOut,author="IMProToo",description="",netcdfFormat = 'NETCDF3_CLASSIC'):
    '''
    writes MRR Average or Instantaneous Data into Netcdf file
  
    @parameter fileOut (str): netCDF file name
    @parameter author (str): Author for netCDF meta data (default:IMProToo)
    @parameter description (str): Description for NetCDF Metadata (default: empty)
    @parameter netcdfFormat (str): netCDF Format (default:NETCDF3_CLASSIC)
'''

   #most syntax between netcdf packages is identical, but there is one nasty difference regarding the fillValue...
    if netcdfFormat in ["NETCDF3_CLASSIC", "NETCDF3_64BIT", "NETCDF4_CLASSIC", "NETCDF4"]:
      import netCDF4 as nc
      pyNc = True
    elif netcdfFormat in ["NETCDF3"]:
      try:
	import Scientific.IO.NetCDF as nc
	pyNc = False
      except:
	#fallback for old netCDF3 with the same syntax as netcdf4!
	import netCDF3 as nc
	pyNc = True
    else:
      raise ValueError("Unknown nc form "+netcdfFormat)
      
    if pyNc: cdfFile = nc.Dataset(fileOut,"w",netcdfFormat)
    else: cdfFile = nc.NetCDFFile(fileOut,"w")
    
    fillVDict = dict()
    #little cheat to avoid hundreds of if, else...
    if pyNc: fillVDict["fill_value"] = missingNumber

    
    print("writing %s ..."%(fileOut))
    #Attributes
    cdfFile.history = 'Created ' + str(time.ctime(time.time()))
    cdfFile.source = 'Created by '+author
    cdfFile.mrrHeader = self.header
    cdfFile.description = description
    
    #Dimensions
    cdfFile.createDimension('MRR rangegate',31)
    cdfFile.createDimension('time', None) #allows Multifile read
    cdfFile.createDimension('MRR spectralclass', 64)
    
    nc_times = cdfFile.createVariable('time','i4',('time',),**fillVDict)
    nc_ranges = cdfFile.createVariable('MRR rangegate','i4',('time', 'MRR rangegate',),**fillVDict)
    nc_classes = cdfFile.createVariable('MRR spectralclass','i4',('MRR spectralclass',))
    
    nc_times.units = 'UNIX Time Stamp'
    nc_ranges.units = 'm'
    nc_classes.units = 'none'
    
    #Create Variables
    nc_tf = cdfFile.createVariable('MRR_TF','f4',('time','MRR rangegate',),**fillVDict)
    nc_tf.units = 'none'
    
    nc_f  = cdfFile.createVariable('MRR_F','f4',('time','MRR rangegate','MRR spectralclass',),**fillVDict)
    nc_f.units = 'dB'
    
    nc_d  = cdfFile.createVariable('MRR_D','f4',('time','MRR rangegate','MRR spectralclass',),**fillVDict)
    nc_d.units = 'm^-3 mm^-1'
    
    nc_n  = cdfFile.createVariable('MRR_N','f4',('time','MRR rangegate','MRR spectralclass',),**fillVDict)
    nc_n.units = '#'
    
    nc_k  = cdfFile.createVariable('MRR_K','f4',('time','MRR rangegate',),**fillVDict)
    nc_k.units = 'dB'
    
    nc_capitalZ  = cdfFile.createVariable('MRR_Capital_Z','f4',('time','MRR rangegate',),**fillVDict)
    nc_capitalZ.units = 'dBz'
    
    nc_smallz  = cdfFile.createVariable('MRR_Small_z','f4',('time','MRR rangegate',),**fillVDict)
    nc_smallz.units = 'dBz'
    
    nc_pia  = cdfFile.createVariable('MRR_PIA','f4',('time','MRR rangegate',),**fillVDict)
    nc_pia.units = 'dB'
    
    nc_rr  = cdfFile.createVariable('MRR_RR','f4',('time','MRR rangegate',),**fillVDict)
    nc_rr.units = 'mm/h'
    
    nc_lwc  = cdfFile.createVariable('MRR_LWC','f4',('time','MRR rangegate',),**fillVDict)
    nc_lwc.units = 'g/m^3'
    
    nc_w  = cdfFile.createVariable('MRR_W','f4',('time','MRR rangegate',),**fillVDict)
    nc_w.units = 'm/s'
    
    
    # fill dimensions
    nc_classes[:] = np.arange(0,64,1)
    nc_times[:] = self.mrrTimestamps
    nc_ranges[:] = self.mrrH

    #fill data
    nc_tf[:] = self.mrrTF
    nc_f[:] = self.mrrF
    nc_d[:] = self.mrrD
    nc_n[:] = self.mrrN
    nc_k[:] = self.mrrK
    nc_capitalZ[:] = self.mrrCapitalZ
    nc_smallz[:] = self.mrrSmallz
    nc_pia[:] = self.mrrPIA
    nc_rr[:] = self.mrrRR
    nc_lwc[:] = self.mrrLWC
    nc_w[:] = self.mrrW
    
    
    if not pyNc: 
      nc_times._FillValue =float(self.missingNumber)
      nc_ranges._FillValue =float(self.missingNumber)  
      nc_tf._FillValue =float(self.missingNumber)
      nc_f._FillValue =float(self.missingNumber)      
      nc_d._FillValue =float(self.missingNumber)     
      nc_n._FillValue =float(self.missingNumber)
      nc_k._FillValue =float(self.missingNumber)  
      nc_capitalZ._FillValue =float(self.missingNumber)
      nc_smallz._FillValue =float(self.missingNumber)      
      nc_pia._FillValue =float(self.missingNumber)     
      nc_rr._FillValue =float(self.missingNumber)
      nc_lwc._FillValue =float(self.missingNumber)  
      nc_w._FillValue =float(self.missingNumber)
    
    
    cdfFile.close()
    print("done")
  #end def write2NetCDF
#end class MrrData

class mrrRawData:
  '''
  Class to read and process MRR raw data
  '''
  
  missingNumber = -9999
  
  def __init__(self,fname,debugStart=0,debugLimit = 0,maskData = True):
    """
    reads MRR raw data. The data is not converted, no magic! The input files can be .gz compressed. Invalid or Missing data is marked as nan and masked
    
    @parameter fname (str): Filename, wildcards allowed!
    @parameter debugstart (int): start after debugstart timestamps
    @parameter debugLimit (int): stop after debugLimit timestamps
    
    provides:
    mrrRawTime (numpy int64): timestamps in seconds since 01-01-1970 (time)
    mrrRawHeight (numpy float64): height levels (time*height)
    mrrRawTF (numpy float64): Transfer function (time*height)
    mrrRawSpectrum (numpy float64): spectral reflectivities of MRR raw data (time*height*velocity)
    """
    
    self.defaultSpecPer10Sec = 58    #only provided in newer Firmware, has to guessed for older ones

    
    #some helper functions
    def rawEsc(string,floatInt):
      """
      set invalid data to nan!
      
      @parameter string (str): string from mrr data
      @parameter floatInt (function): int or float function

      @return - float or int number
      """

      if (string == " "*9) or (len(string)!=9):
        return np.nan
      else:
        return floatInt(string)  


    def splitMrrRawData(string,debugTime,floatInt):
      '''
      splits one line of mrr raw data into list
      @parameter string (str) string of MRR data
      @parameter debugTime (int) time for debug output
      @parameter floatInt (type) convert float or integer
      
      @retrun array with mrr data
      '''

      instData = list()
      instData_append = instData.append
      for k in np.arange(6,9*32,9):
        try:
          instData_append(rawEsc(string[k:k+9],floatInt))
        except:
          print("######### Warning, Corrupt data at "+ str(IMProTooTools.unix2date(debugTime))+ ", position "+str(k)+": " + string+" #########")
          instData_append(np.nan)
      return np.array(instData)

    files = glob.glob(fname)
    files.sort()

    foundAtLeastOneFile = False
    
    #go thorugh all files
    for f,file in enumerate(files):
      print "%s of %s:"%(f+1,len(files)), file
      #open file gz or ascii
      try:
        if file[-3:]==".gz":
          try: allData = gzip.open(file, 'rb')
          except: 
            print "could not open:", file
            raise IOError("could not open:"+ file)
        else:
          try: allData = open(file, 'r')
          except: 
            print "could not open:", file
            raise IOError("could not open:"+ file)
      
        if len(allData.read(10))==0:
          print file, "empty!"
          allData.close()
          raise IOError("File empty")
        else:
          allData.seek(0)
          i=0
      except IOError:
        print "skipping..."
        continue
      
      foundAtLeastOneFile = True
      
      #go through file and make a dictionary with timestamp as key and all corresponding lines of data as values
      dataMRR = {}
      prevDate=0
      tmpList = list()
      for line in allData:
        if line[0:2] == "T:":
          if i != 0:
            dataMRR[prevDate] = tmpList
          tmpList = []
          asciiDate = line[2:14]
          # Script wants UTC!
          if ( re.search("UTC", line) == None):
            sys.exit("Warning, must be UTC!")
          date = datetime.datetime(year = 2000+int(asciiDate[0:2]), month = int(asciiDate[2:4]), day = int(asciiDate[4:6]), hour = int(asciiDate[6:8]), minute = int(asciiDate[8:10]), second = int(asciiDate[10:12]))
          date = int(IMProTooTools.date2unix(date))
          tmpList.append(line)
          prevDate = date
        else:
            tmpList.append(line)
        i += 1
      #end for line
      dataMRR[prevDate] = tmpList
      allData.close()
      
      try:
        del dataMRR[0]
        print "Warning: some lines without timestamp"
      except:
        print "",
    
      if debugLimit == 0:
        debugLimit = len(dataMRR.keys())
        
      specLength = debugLimit - debugStart
      
      #create arrays for data
      rawSpectra = np.ones((specLength,32,64),dtype=int)*np.nan
      rawTimestamps = np.array(np.sort(dataMRR.keys())[debugStart:debugLimit],dtype=int)
      rawHeights = np.ones((specLength,32),dtype=int)*np.nan
      rawTFs =  np.ones((specLength,32),dtype=float)*np.nan
      rawNoSpec =  np.zeros(specLength,dtype=int)
      
      #go through timestamps and fill up arrays
      for t,timestamp in enumerate(rawTimestamps):
        dataSet = dataMRR[timestamp]
        for dataLine in dataSet:
          if dataLine[0:2] == "T:":
            if t == 1:
              self.header = dataLine[19:-2]  # just one is stored, thus no array
              if dataLine[39:41] == 'CC':
                try: self.mrrRawCC = int(dataLine[42:49])
                except: 
                  print('Warning, colud not read CC:'+dataLine[42:49])
                  self.mrrRawCC = 0
              else:
                print('Warning, colud not find Keyword CC in :'+dataLine[39:41])
                self.mrrRawCC = 0
            #TODO: update to newest firmware!
            if dataLine[39:41] == 'enter here keyword for number of spectra':
              try: 
                rawNoSpec[t] == int(dataLine[19:-2])
              except: 
                print('Warning, colud not read number of Spectra: "'+dataLine[0:1]+'", taking default instead: '+self.defaultSpecPer10Sec)
                rawNoSpec[t] = self.defaultSpecPer10Sec
            else:
              #this is standard for older software Versions, thus no warning is raised.
              rawNoSpec[t] = self.defaultSpecPer10Sec
            continue #print timestamp
          elif dataLine[0:3] == "M:h":
            rawHeights[t,:] = splitMrrRawData(dataLine,timestamp,int)
            continue #print "H"
          elif dataLine[0:4] == "M:TF":
            rawTFs[t,:] = splitMrrRawData(dataLine,timestamp,float)
            continue #print "TF"
          elif dataLine[0:3] == "M:f":
            try:
              specBin = int(dataLine[3:5])
            except:
              print("######### Warning, Corrupt data header at "+ str(IMProTooTools.unix2date(timestamp))+ ", " + dataLine+" #########")
              continue
            rawSpectra[t,:,specBin] = splitMrrRawData(dataLine,timestamp,int)
            continue
          elif (dataLine[0:4] == "C:VS") or (dataLine[0:4] == "C:VT") or (dataLine[0:3] == "R:V") or (dataLine[0:3] == "R:v"):
            continue
          else:
            print "? Line not recognized:", dataLine
            
      #end for t,timestamp
      
      #discard spectra which are only partly valid!
      rawSpectra[np.any(np.isnan(rawSpectra),axis=2)] = np.nan
      
      #join arrays of different days
      try:
        self.mrrRawHeight = np.concatenate((self.mrrRawHeight,rawHeights),axis=0)
        self.mrrRawTime = np.concatenate((self.mrrRawTime, rawTimestamps),axis=0)
        self.mrrRawTF = np.concatenate((self.mrrRawTF,rawTFs),axis=0)
        self.mrrRawSpectrum = np.concatenate((self.mrrRawSpectrum, rawSpectra),axis=0)
        self.mrrRawNoSpec = np.concatenate((self.mrrRawNoSpec, rawNoSpec),axis=0)
      except AttributeError:
        self.mrrRawHeight = rawHeights
        self.mrrRawTime = rawTimestamps
        self.mrrRawTF = rawTFs
        self.mrrRawSpectrum = rawSpectra
        self.mrrRawNoSpec = rawNoSpec
      #end try
    #end for f,file
    
    if foundAtLeastOneFile == False:
      raise UnboundLocalError("No files found: "+ fname)
    try: self.header
    except:
      print "did not find any MRR data in file!"
      raise IOError("did not find any MRR data in file!")
    del rawHeights, rawTimestamps, rawTFs, rawSpectra
    
    if maskData:
      self.mrrRawHeight = np.ma.masked_array(self.mrrRawHeight,np.isnan(self.mrrRawHeight))
      self.mrrRawTime = np.ma.masked_array(self.mrrRawTime,np.isnan(self.mrrRawTime))
      self.mrrRawTF = np.ma.masked_array(self.mrrRawTF,np.isnan(self.mrrRawTF))
      self.mrrRawSpectrum = np.ma.masked_array(self.mrrRawSpectrum,np.isnan(self.mrrRawSpectrum))
    
    self.shape2D = np.shape(self.mrrRawHeight)
    self.shape3D = np.shape(self.mrrRawSpectrum)

  #end def __init__
  
  def write2NetCDF(self,fileOut,author="IMProToo",description="",netcdfFormat = 'NETCDF3_CLASSIC'):
    '''
    writes MRR raw Data into Netcdf file
  
    @parameter fileOut (str): netCDF file name
    @parameter author (str): Author for netCDF meta data (default:IMProToo)
    @parameter description (str): Description for NetCDF Metadata (default: empty)
    @parameter netcdfFormat (str): , possible values are NETCDF3_CLASSIC, NETCDF3_64BIT, NETCDF4_CLASSIC, and NETCDF4 for the python-netcdf4 package (NETCDF3_CLASSIC gives netcdf4 files for newer ubuntu versions!!) NETCDF3 takes the "old" Scientific.IO.NetCDF module, which is a bit more convinient or as fall back option python-netcdf3
    '''
   #most syntax between netcdf packages is identical, but there is one nasty difference regarding the fillValue...
    if netcdfFormat in ["NETCDF3_CLASSIC", "NETCDF3_64BIT", "NETCDF4_CLASSIC", "NETCDF4"]:
      import netCDF4 as nc
      pyNc = True
    elif netcdfFormat in ["NETCDF3"]:
      try:
	import Scientific.IO.NetCDF as nc
	pyNc = False
      except:
	#fallback for old netCDF3 with the same syntax as netcdf4!
	import netCDF3 as nc
	pyNc = True
    else:
      raise ValueError("Unknown nc form "+netcdfFormat)
      
    if pyNc: cdfFile = nc.Dataset(fileOut,"w",netcdfFormat)
    else: cdfFile = nc.NetCDFFile(fileOut,"w")
    
    print("writing %s ..."%(fileOut))
    #Attributes
    cdfFile.history = 'Created ' + str(time.ctime(time.time()))
    cdfFile.source = 'Created by '+author
    cdfFile.mrrHeader = self.header
    cdfFile.description = description
    cdfFile.mrrCalibrationConstant = self.mrrRawCC
    
    fillVDict = dict()
    #little cheat to avoid hundreds of if, else...
    if pyNc: fillVDict["fill_value"] = missingNumber
    
    #Dimensions
    cdfFile.createDimension('MRR rangegate',32)
    cdfFile.createDimension('time', None) #allows Multifile read
    cdfFile.createDimension('MRR spectralclass', 64)
    
    nc_times = cdfFile.createVariable('MRR time','i4',('time',),**fillVDict)
    nc_ranges = cdfFile.createVariable('MRR rangegate','i4',('time', 'MRR rangegate',))
    nc_classes = cdfFile.createVariable('MRR spectralclass','i4',('MRR spectralclass',),**fillVDict)
    
    nc_times.units = 'UNIX Time Stamp'
    nc_ranges.units = 'm'
    nc_classes.units = 'none'
    
    #Create Variables
    nc_tf = cdfFile.createVariable('MRR_TF','f4',('time','MRR rangegate',),**fillVDict)
    nc_tf.units = 'none'

    
    nc_spectra  = cdfFile.createVariable('MRR_Spectra','f4',('time','MRR rangegate','MRR spectralclass',),**fillVDict)
    nc_spectra.units = 'none'

    
    nc_noSpec  = cdfFile.createVariable('MRR_NoSpectra','i4',('time',),**fillVDict)
    nc_noSpec.units = 'none'

    
    # fill dimensions
    nc_classes[:] = np.arange(0,64,1)
    nc_times[:] = self.mrrRawTime
    nc_ranges[:] = self.mrrRawHeight

    #fill data
    nc_tf[:] = self.mrrRawTF
    nc_spectra[:] = self.mrrRawSpectrum
    nc_noSpec[:] = self.mrrRawNoSpec
    
    if not pyNc: 
      nc_noSpec._FillValue =float(self.missingNumber)
      nc_spectra._FillValue =float(self.missingNumber)      
      nc_tf._FillValue =float(self.missingNumber)     
      nc_times._FillValue =float(self.missingNumber)
      nc_ranges._FillValue =float(self.missingNumber)      
    
    cdfFile.close()
    print("done")
  #end def write2NetCDF
#end class MrrData
