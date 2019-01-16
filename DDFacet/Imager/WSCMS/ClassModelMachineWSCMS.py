'''
DDFacet, a facet-based radio imaging package
Copyright (C) 2013-2016  Cyril Tasse, l'Observatoire de Paris,
SKA South Africa, Rhodes University

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
'''

import numpy as np
from DDFacet.Other import MyLogger
from DDFacet.Other import ModColor
log=MyLogger.getLogger("ClassModelMachine")
from DDFacet.Array import NpParallel
from DDFacet.ToolsDir import ModFFTW
from DDFacet.Other import MyPickle
from DDFacet.Other import reformat
from DDFacet.ToolsDir.Gaussian import GaussianSymmetric
from DDFacet.ToolsDir.GiveEdges import GiveEdges
from DDFacet.Imager import ClassModelMachine as ClassModelMachinebase
from DDFacet.Imager import ClassFrequencyMachine, ClassScaleMachine
import os

class ClassModelMachine(ClassModelMachinebase.ClassModelMachine):
    def __init__(self,*args,**kwargs):
        ClassModelMachinebase.ClassModelMachine.__init__(self, *args, **kwargs)
        self.DicoSMStacked={}
        self.DicoSMStacked["Type"]="WSCMS"
        self.n_sub_minor_iter = 0

    def setRefFreq(self, RefFreq, Force=False):
        if self.RefFreq is not None and not Force:
            print>>log, ModColor.Str("Reference frequency already set to %f MHz" % (self.RefFreq/1e6))
            return

        self.RefFreq = RefFreq
        self.DicoSMStacked["RefFreq"] = RefFreq

    def setPSFServer(self, PSFServer):
        self.PSFServer = PSFServer

        _, _, self.Npix, _ = self.PSFServer.ImageShape
        self.NpixPadded = int(np.ceil(self.GD["Facets"]["Padding"] * self.Npix))
        # make sure it is odd numbered
        if self.NpixPadded % 2 == 0:
            self.NpixPadded += 1
        self.Npad = (self.NpixPadded - self.Npix) // 2

    def setFreqMachine(self, GridFreqs, DegridFreqs, weights=None, PSFServer=None):
        self.PSFServer = PSFServer
        # Initiaise the Frequency Machine
        self.DegridFreqs = DegridFreqs
        self.GridFreqs = GridFreqs
        self.FreqMachine = ClassFrequencyMachine.ClassFrequencyMachine(GridFreqs, DegridFreqs,
                                                                       self.DicoSMStacked["RefFreq"], self.GD,
                                                                       weights=weights, PSFServer=self.PSFServer)
        self.FreqMachine.set_Method()

        if (self.GD["Freq"]["NBand"] > 1):
            self.Coeffs = np.zeros(self.GD["WSCMS"]["NumFreqBasisFuncs"])
        else:
            self.Coeffs = np.zeros([1])

        self.Nchan = self.FreqMachine.nchan
        self.Npol = 1

        # self.DicoSMStacked["Eval_Degrid"] = self.FreqMachine.Eval_Degrid


    def setScaleMachine(self, PSFServer, NCPU=None, MaskArray=None, FTMachine=None, cachepath=None):
        if self.GD["WSCMS"]["MultiScale"]:
            if NCPU is None:
                self.NCPU = self.GD['Parallel'][NCPU]
                if self.NCPU == 0:
                    import multiprocessing

                    self.NCPU = multiprocessing.cpu_count()
            else:
                 self.NCPU = NCPU
            self.DoAbs = self.GD["Deconv"]["AllowNegative"]
            self.ScaleMachine = ClassScaleMachine.ClassScaleMachine(GD=self.GD, NCPU=NCPU, MaskArray=MaskArray)
            self.FTMachine = FTMachine
            self.ScaleMachine.Init(PSFServer, self.FreqMachine,
                                   cachepath=cachepath)
            self.Nscales = self.ScaleMachine.Nscales
            # Initialise CurrentScale variable
            self.CurrentScale = 999999
            # Initialise current facet variable
            self.CurrentFacet = 999999


            self.DicoSMStacked["Scale_Info"] = {}
            for iScale, sigma in enumerate(self.ScaleMachine.sigmas):
                if iScale not in self.DicoSMStacked["Scale_Info"].keys():
                    self.DicoSMStacked["Scale_Info"][iScale] = {}
                self.DicoSMStacked["Scale_Info"][iScale]["sigma"] = self.ScaleMachine.sigmas[iScale]
                self.DicoSMStacked["Scale_Info"][iScale]["kernel"] = self.ScaleMachine.kernels[iScale]
                self.DicoSMStacked["Scale_Info"][iScale]["extent"] = self.ScaleMachine.extents[iScale]

        else:
            # we need to keep track of what the sigma value of the delta scale corresponds to
            # even if we don't do multiscale (because we need it in GiveModelImage)
            (self.FWHMBeamAvg, _, _) = PSFServer.DicoVariablePSF["EstimatesAvgPSF"]
            self.ListScales = [1.0/np.sqrt(2)*((self.FWHMBeamAvg[0] + self.FWHMBeamAvg[1])*np.pi / 180) / \
                                (2.0 * self.GD['Image']['Cell'] * np.pi / 648000)]

    def ToFile(self, FileName, DicoIn=None):
        print>> log, "Saving dico model to %s" % FileName
        if DicoIn is None:
            D = self.DicoSMStacked
        else:
            D = DicoIn

        D["GD"] = self.GD
        D["Type"] = "WSCMS"
        try:
            D["ListScales"] = list(self.ScaleMachine.sigmas)  # list containing std of Gaussian components
        except:
            D["ListScales"] = self.ListScales
        D["ModelShape"] = self.ModelShape
        MyPickle.Save(D, FileName)

    def FromFile(self, FileName):
        print>> log, "Reading dico model from %s" % FileName
        self.DicoSMStacked = MyPickle.Load(FileName)
        self.FromDico(self.DicoSMStacked)

    def FromDico(self, DicoSMStacked):
        self.DicoSMStacked = DicoSMStacked
        self.RefFreq = self.DicoSMStacked["RefFreq"]
        self.ListScales = self.DicoSMStacked["ListScales"]
        self.ModelShape = self.DicoSMStacked["ModelShape"]

    def setModelShape(self, ModelShape):
        self.ModelShape = ModelShape
        self.Npix = self.ModelShape[-1]

    def AppendComponentToDictStacked(self, key, Sols, iScale, Gain):
        """
        Adds component to model dictionary at a scale specified by Scale. 
        The dictionary corresponding to each scale is keyed on pixel values (l,m location tupple). 
        Each model component is therefore represented parametrically by a pixel value a scale and a set of coefficients
        associated with the spectral function that is fit to the frequency axis.
        Currently only Stokes I is supported.
        Args:
            key: the (l,m) centre of the component
            Fpol: Weight of the solution
            Sols: Nd array of solutions with length equal to the number of basis functions representing the component.
            Scale: the sigma value (Gaussian standard deviation) of the scale at which to append the component    
        Post conditions:
        Added component list to dictionary for particular scale. This dictionary is stored in
        self.DicoSMStacked["Comp"][Scale] and has keys:
            "SolsArray": solutions ndArray with shape [#basis_functions,#stokes_terms]
            "SumWeights": weights ndArray with shape [#stokes_terms]
            
            
        LB - Note I have added and extra scale layer to the dictionary structure
        """
        DicoComp = self.DicoSMStacked.setdefault("Comp", {})

        if iScale not in DicoComp.keys():
            DicoComp[iScale] = {}
            DicoComp[iScale]["NumComps"] = np.zeros(1, np.int16)  # keeps track of number of components at this scale

        if key not in DicoComp[iScale].keys():
            DicoComp[iScale][key] = {}
            DicoComp[iScale][key]["SolsArray"] = np.zeros(Sols.size, np.float32)

        DicoComp[iScale]["NumComps"] += 1
        DicoComp[iScale][key]["SolsArray"] += Sols.ravel() * Gain

    def GiveModelImage(self, FreqIn=None, out=None):
        RefFreq=self.DicoSMStacked["RefFreq"]
        # Default to reference frequency if no input given
        if FreqIn is None:
            FreqIn=np.array([RefFreq], dtype=np.float32)

        FreqIn = np.array([FreqIn.ravel()], dtype=np.float32).flatten()

        DicoComp = self.DicoSMStacked.setdefault("Comp", {})
        _, npol, nx, ny = self.ModelShape

        # The model shape has nchan = len(GridFreqs)
        nchan = FreqIn.size
        if out is not None:  # LB - is this for appending components to an existing model?
            if out.shape != (nchan,npol,nx,ny) or out.dtype != np.float32:
                raise RuntimeError("supplied image has incorrect type (%s) or shape (%s)" % (out.dtype, out.shape))
            ModelImage = out
        else:
            ModelImage = np.zeros((nchan,npol,nx,ny),dtype=np.float32)

        # # get the zero scale
        # try:
        #     zero_scale = self.ScaleMachine.sigmas[0]
        # except:
        #     zero_scale = self.ListScales[0]

        for iScale in DicoComp.keys():
            # Note here we are building a spectral cube delta function representation first and then convolving by
            # the scale at the end
            ScaleModel = np.zeros((nchan, npol, nx, ny), dtype=np.float32)
            # get scale kernel
            if self.GD["WSCMS"]["MultiScale"]:
                sigma = self.DicoSMStacked["Scale_Info"][iScale]["sigma"]
                kernel = self.DicoSMStacked["Scale_Info"][iScale]["kernel"]
                extent = self.DicoSMStacked["Scale_Info"][iScale]["extent"]

            for key in DicoComp[iScale].keys():
                if key != "NumComps":
                    Sol = DicoComp[iScale][key]["SolsArray"]
                    # TODO - try soft thresholding components
                    x, y = key
                    try:  # LB - Should we drop support for anything other than polynomials maybe?
                        interp = self.FreqMachine.Eval_Degrid(Sol, FreqIn)
                    except:
                        interp = np.polyval(Sol[::-1], FreqIn/RefFreq)

                    if interp is None:
                        raise RuntimeError("Could not interpolate model onto degridding bands. Inspect your data, check "
                                           "'WSCMS-NumFreqBasisFuncs' or if you think this is a bug report it.")

                    if self.GD["WSCMS"]["MultiScale"] and iScale != 0:
                        Aedge, Bedge = GiveEdges((x, y), nx, (extent // 2, extent // 2), extent)

                        x0d, x1d, y0d, y1d = Aedge
                        x0p, x1p, y0p, y1p = Bedge
                        try:
                            out = np.atleast_1d(interp)[:, None, None, None] * kernel
                            ScaleModel[:, :, x0d:x1d, y0d:y1d] += out[:, :, x0p:x1p, y0p:y1p]
                        except:
                            x -= nx // 2
                            y -= ny // 2
                            ScaleModel += GaussianSymmetric(sigma, nx, x0=x or None,
                                                            y0=y or None, amp=interp, cube=True)
                    else:
                        ScaleModel[:, 0, x, y] += interp

            ModelImage += ScaleModel
        # print "Model - ", ModelImage.max(), ModelImage.min()
        return ModelImage

    def GiveSpectralIndexMap(self, GaussPars=[(1, 1, 0)], ResidCube=None,
                                GiveComponents=False, ChannelWeights=None):

        # convert to radians
        ex, ey, pa = GaussPars
        ex *= np.pi/180
        ey *= np.pi/180
        pa *= np.pi/180

        # get in terms of number of cells
        CellSizeRad = self.GD['Image']['Cell'] * np.pi / 648000
        # ex /= self.GD['Image']['Cell'] * np.pi / 648000
        # ey /= self.GD['Image']['Cell'] * np.pi / 648000

        # get Gaussian kernel
        GaussKern = ModFFTW.GiveGauss(self.Npix, CellSizeRad=CellSizeRad, GaussPars=(ex, ey, pa), parallel=False)
        # normalise
        # GaussKern /= np.sum(GaussKern.flatten())
        # take FT
        Fs = np.fft.fftshift
        iFs = np.fft.ifftshift
        npad = self.Npad
        FTarray = self.ScaleMachine.FTMachine.xhatim.view()
        print
        FTarray[...] = iFs(np.pad(GaussKern[None, None], ((0, 0), (0, 0), (npad, npad), (npad, npad)),
                             mode='constant'), axes=(2, 3))
        # this puts the FT in FTarray
        self.ScaleMachine.FTMachine.FFTim()
        # need to copy since FTarray and FTcube are views to the same array
        FTkernel = FTarray.copy()

        # evaluate model
        ModelImage = self.GiveModelImage(self.GridFreqs)

        # pad and take FT
        FTcube = self.ScaleMachine.FTMachine.Chatim.view()
        FTcube[...] = iFs(np.pad(ModelImage, ((0, 0), (0, 0), (npad, npad), (npad, npad)),
                                 mode='constant'), axes=(2, 3))
        self.ScaleMachine.FTMachine.CFFTim()

        # multiply by kernel
        FTcube *= FTkernel

        # take iFT
        self.ScaleMachine.FTMachine.iCFFTim()

        I = slice(npad, -npad)

        ConvModelImage = Fs(FTcube, axes=(2,3))[:, :, I, I].real

        if ResidCube is not None:
            ConvModelImage += ResidCube

        ConvModelImage = ConvModelImage.squeeze()

        RMS = np.std(ResidCube.flatten())
        Threshold = self.GD["SPIMaps"]["AlphaThreshold"] * RMS

        # get minimum along any freq axis
        MinImage = np.amin(ConvModelImage, axis=0)
        MaskIndices = np.argwhere(MinImage > Threshold)
        FitCube = ConvModelImage[:, MaskIndices[:, 0], MaskIndices[:, 1]]

        if ChannelWeights is None:
            weights = np.ones(self.Nchan, dtype=np.float32)
        else:
            weights = ChannelWeights.astype(np.float32)
            if ChannelWeights.size != self.Nchan:
                import warnings
                warnings.warn("The provided channel weights are of incorrect length. Ignoring weights.", RuntimeWarning)
                weights = np.ones(self.Nchan, dtype=np.float32)



        try:
            import traceback
            from africanus.model.spi.dask import fit_spi_components
            NCPU = self.GD["Parallel"]["NCPU"]
            if NCPU:
                from multiprocessing.pool import ThreadPool
                import dask

                dask.config.set(pool=ThreadPool(NCPU))
            else:
                import multiprocessing
                NCPU = multiprocessing.cpu_count()

            import dask.array as da
            _, ncomps = FitCube.shape
            FitCubeDask = da.from_array(FitCube.T.astype(np.float64), chunks=(ncomps//NCPU, self.Nchan))
            weightsDask = da.from_array(weights.astype(np.float64), chunks=(self.Nchan))
            freqsDask = da.from_array(self.GridFreqs.astype(np.float64), chunks=(self.Nchan))

            alpha, varalpha, Iref, varIref = fit_spi_components(FitCubeDask, weightsDask,
                                                                freqsDask, self.RefFreq,
                                                                dtype=np.float64).compute()
        except Exception as e:
            traceback_str = traceback.format_exc(e)
            print>>log, "Warning - Failed at importing africanus spi fitter. This could be an issue with the dask " \
                        "version. Falling back to (slow) scipy version"
            print>>log, "Original traceback - ", traceback_str
            alpha, varalpha, Iref, varIref = self.FreqMachine.FitSPIComponents(FitCube, self.GridFreqs, self.RefFreq)

        _, _, nx, ny = ModelImage.shape
        alphamap = np.zeros([nx, ny])
        Irefmap = np.zeros([nx, ny])
        alphastdmap = np.zeros([nx, ny])
        Irefstdmap = np.zeros([nx, ny])

        alphamap[MaskIndices[:, 0], MaskIndices[:, 1]] = alpha
        Irefmap[MaskIndices[:, 0], MaskIndices[:, 1]] = Iref
        alphastdmap[MaskIndices[:, 0], MaskIndices[:, 1]] = np.sqrt(varalpha)
        Irefstdmap[MaskIndices[:, 0], MaskIndices[:, 1]] = np.sqrt(varIref)

        if GiveComponents:
            return alphamap[None, None], alphastdmap[None, None], alpha
        else:
            return alphamap[None, None], alphastdmap[None, None]

    def SubStep(self, (dx, dy), LocalSM, Residual):
        """
        Sub-minor loop subtraction
        """
        xc, yc = dx, dy
        N0 = Residual.shape[-1]
        N1 = LocalSM.shape[-1]

        # Get overlap indices where psf should be subtracted
        Aedge, Bedge = GiveEdges((xc, yc), N0, (N1 // 2, N1 // 2), N1)

        x0d, x1d, y0d, y1d = Aedge
        x0p, x1p, y0p, y1p = Bedge

        # Subtract from each channel/band
        Residual[:, :, x0d:x1d, y0d:y1d] -= LocalSM[:, :, x0p:x1p, y0p:y1p]

        return Residual

    def set_ConvPSF(self, iFacet, iScale):
        # we only need to compute the PSF if Facet or Scale has changed
        # note will always be set initially since comparison to 999999 will fail
        if iFacet != self.CurrentFacet or self.CurrentScale != iScale:
            key = 'S' + str(iScale) + 'F' + str(iFacet)
            # update facet (need to make sure PSFserver has been updated when we get here)
            self.CurrentFacet = iFacet

            # update scale
            self.CurrentScale = iScale

            # get the gain in this Facet for this scale. This function actually does most of the work.
            # If the PSF's for this facet and scale have not yet been computed it will compute them and store
            # all the relevant information in the LRU cache which spills to disk automatically if the number
            # of elements exceeds the pre-set maximum in --WSCMS-CacheSize
            self.CurrentGain = self.ScaleMachine.give_gain(iFacet, iScale)

            # print "Scale = ", self.CurrentScale, " gain = ", self.CurrentGain

            # twice convolve PSF with scale if not delta scale
            if not iScale:
                PSF, PSFmean = self.PSFServer.GivePSF()
                self.ConvPSF = PSF
                #self.ConvPSFmean = PSFmean
                # delta scale is not cleaned with the ConvPSF so these should all be unity
                self.PSFFreqNormFactors = np.ones([self.Nchan, 1, 1, 1], dtype=np.float32)
                self.FpolNormFactor = 1.0

            else:
                self.ConvPSF = self.ScaleMachine.Conv2PSFs[key]

                # To normalise by the frequency response of ConvPSF implicitly contained in the residual
                # we need to keep track of the ConvPSF peaks. Note this is not done in wsclean but should give more
                # even per band residuals
                self.PSFFreqNormFactors = self.ScaleMachine.ConvPSFFreqPeaks[key]

                # This normalisation for Fpol is required so that we don't see jumps between minor cycles.
                # Basically, since the PSF is normalised by this factor the components also need to be normalised
                # by the same factor for the subtraction in the sub-minor cycle to be the same as the subtraction
                # in the minor and major cycles.
                self.FpolNormFactor = self.ScaleMachine.ConvPSFNormFactor


    def give_scale_mask(self, meanDirty, meanPSF, gain):
        """
        Automatically creates a mask for this scale by doing a shallow clean meanDirty 
        :param meanDirty: The mean dirty image convolved with scale function for the current scale 
        :param meanPSF: The mean PSF twice convolved with the scale function for the current scale
        :param gain: scale dependent gain
        :return: 
        """
        x, y, MaxDirty = NpParallel.A_whereMax(meanDirty, NCPU=self.NCPU, DoAbs=self.DoAbs,
                                               Mask=self.ScaleMachine.MaskArray)

        mask = np.ones_like(meanDirty, dtype=np.bool)

        threshold = 0.9*np.abs(MaxDirty)

        i = 0
        maxit = 100
        while i < maxit and np.abs(MaxDirty) > threshold:
            val = meanDirty[0, 0, x, y]
            # print i, val, gain*val*meanPSF[0,0,:,:].max(), val - gain*val*meanPSF[0,0,:,:].max()
            mask[:, :, x, y] = 0
            meanDirty = self.SubStep((x, y), gain*val*meanPSF, meanDirty)
            x, y, MaxDirty = NpParallel.A_whereMax(meanDirty, NCPU=self.NCPU, DoAbs=self.DoAbs,
                                                   Mask=self.ScaleMachine.MaskArray)
            i += 1
        # if i >= maxit:
        #     print "Warning - max iterations reached"
        return mask


    def do_minor_loop(self, x, y, Dirty, meanDirty, JonesNorm, W, MaxDirty, Stopping_flux=None):
        """
        Runs the sub-minor loop at a specific scale 
        :param Dirty: 
        :param meanDirty: 
        :param JonesNorm: 
        :return: The scale convolved model and a list of components 
        """
        # determine most relevant scale. This is the most time consuming step hence the sub-minor cycle
        xscale, yscale, ConvMaxDirty, CurrentDirty, ConvDirtyCube, iScale,  = \
            self.ScaleMachine.do_scale_convolve(Dirty.copy(), meanDirty.copy())
        if iScale == 0:
            xscale = x
            yscale = y
            ConvMaxDirty = MaxDirty
            CurrentDirty = meanDirty.view()
            ConvDirtyCube = Dirty.view()

        # print "iScale = ", iScale

        # set PSF at current location
        self.PSFServer.setLocation(xscale, yscale)

        # get GaussPars for scale
        sigma = self.ScaleMachine.sigmas[iScale]
        extent = self.ScaleMachine.extents[iScale]
        kernel = self.ScaleMachine.kernels[iScale]

        # set twice convolve PSF for scale and facet if either has changed
        self.set_ConvPSF(self.PSFServer.iFacet, iScale)

        # update scale dependent mask
        if self.GD["WSCMS"]["AutoMask"]:
            mask = self.give_scale_mask(CurrentDirty.copy(),
                                        self.ScaleMachine.Conv2PSFmean[str(iScale)],
                                        self.CurrentGain)
            if str(iScale) not in self.ScaleMachine.ScaleMaskArray:
                self.ScaleMachine.ScaleMaskArray[str(iScale)] = np.ones_like(meanDirty, dtype=np.bool)
            self.ScaleMachine.ScaleMaskArray[str(iScale)] &= mask
            CurrentMask = self.ScaleMachine.ScaleMaskArray[str(iScale)].view()
        else:
            CurrentMask = self.ScaleMachine.MaskArray

        # Create new component list
        Component_list = {}

        # Set stopping threshold.
        # We cannot use StoppingFlux from minor cycle directly since the maxima of the scale convolved residual
        # is different from the maximum of the residual
        Threshold = self.ScaleMachine.PeakFactor * ConvMaxDirty
        if iScale:
            DirtyRatio = ConvMaxDirty / MaxDirty
            # scale_fact = self.ScaleMachine.FWHMs[iScale]/self.ScaleMachine.FWHMs[0]
            Threshold = Threshold * DirtyRatio * self.GD["WSCMS"]["ThresholdBias"] ** (iScale + 1)
        else:
            if Stopping_flux is not None:
                Threshold = np.maximum(Threshold, Stopping_flux)

        # run subminor loop
        k = 0
        while np.abs(ConvMaxDirty) > Threshold and k < self.ScaleMachine.NSubMinorIter:
            # get JonesNorm
            JN = JonesNorm[:, 0, xscale, yscale]

            # set facet location
            self.PSFServer.setLocation(xscale, yscale)

            # set PSF and gain
            self.set_ConvPSF(self.PSFServer.iFacet, iScale)

            # JonesNorm is corrected for in FreqMachine so we just need to pass in the apparent
            Fpol = np.zeros([self.Nchan, 1, 1, 1], dtype=np.float32)
            Fpol[:, 0, 0, 0] = ConvDirtyCube[:, 0, xscale, yscale].copy()

            # correct for frequency response of PSF when convolving with scale function
            Fpol *= self.PSFFreqNormFactors

            # Fit frequency axis to get coeffs (coeffs correspond to intrinsic flux)
            self.Coeffs = self.FreqMachine.Fit(Fpol[:, 0, 0, 0], JN, CurrentDirty[0, 0, xscale, yscale])

            # Overwrite with polynoimial fit (Fpol is apparent flux)
            Fpol[:, 0, 0, 0] = self.FreqMachine.Eval(self.Coeffs)

            self.AppendComponentToDictStacked((xscale, yscale), self.Coeffs / self.FpolNormFactor, self.CurrentScale,
                                              self.CurrentGain)

            # Keep track of apparent model components (this is for subtraction in the upper minor loop, not relevant if
            # its the delta scale)
            if iScale != 0:
                xy = (xscale, yscale)
                Component_list.setdefault(xy, np.zeros([self.Nchan, 1, 1, 1], dtype=np.float32))
                Component_list[xy] += self.CurrentGain * Fpol / self.FpolNormFactor

            # Restore ConvPSF frequency response and subtract component from residual
            Fpol /= self.PSFFreqNormFactors
            ConvDirtyCube = self.SubStep((xscale, yscale), self.ConvPSF * Fpol * self.CurrentGain,
                                         ConvDirtyCube)

            # get the weighted mean over freq axis
            CurrentDirty[...] = np.sum(ConvDirtyCube * W.reshape((W.size, 1, 1, 1)), axis=0)[None, :, :, :]

            # find the peak
            #PeakMap = np.ascontiguousarray(CurrentDirty*self.ScaleMachine.ScaleMaskArray[sigma])
            xscale, yscale, ConvMaxDirty = NpParallel.A_whereMax(CurrentDirty, NCPU=self.NCPU, DoAbs=self.DoAbs,
                                                                 Mask=CurrentMask)

            # Update counters TODO - should add subminor cycle count to minor cycle count
            k += 1
            self.n_sub_minor_iter += 1

        # report if max sub-iterations exceeded
        if k >= self.ScaleMachine.NSubMinorIter:
            print>>log, "Maximum subiterations reached. "

        # print "Value at end = ", CurrentDirty[0, 0, xscale, yscale]

        # Add components onto grid (not needed if we are cleaning the delta scale)
        if iScale:
            # create a model for this scale
            ScaleModel = np.zeros_like(ConvDirtyCube, dtype=np.float32)
            for xy in Component_list.keys():
                x, y = xy
                # get overlap indices
                Aedge, Bedge = GiveEdges((x, y), self.Npix, (extent // 2, extent // 2), extent)
                x0d, x1d, y0d, y1d = Aedge
                x0p, x1p, y0p, y1p = Bedge
                # Note apparent since we convolve with a normalised PSF
                out = Component_list[xy] * kernel
                ScaleModel[:, :, x0d:x1d, y0d:y1d] += out[:, :, x0p:x1p, y0p:y1p]

            return ScaleModel, iScale, xscale, yscale
        else:
            return None, iScale, xscale, yscale



###################### Dark magic below this line ###################################
    def PutBackSubsComps(self):
        # if self.GD["Data"]["RestoreDico"] is None: return

        SolsFile = self.GD["DDESolutions"]["DDSols"]
        if not (".npz" in SolsFile):
            Method = SolsFile
            ThisMSName = reformat.reformat(os.path.abspath(self.GD["Data"]["MS"]), LastSlash=False)
            SolsFile = "%s/killMS.%s.sols.npz" % (ThisMSName, Method)
        DicoSolsFile = np.load(SolsFile)
        SourceCat = DicoSolsFile["SourceCatSub"]
        SourceCat = SourceCat.view(np.recarray)
        # RestoreDico=self.GD["Data"]["RestoreDico"]
        RestoreDico = DicoSolsFile["ModelName"][()][0:-4] + ".DicoModel"

        print>> log, "Adding previously subtracted components"
        ModelMachine0 = ClassModelMachine(self.GD)

        ModelMachine0.FromFile(RestoreDico)

        _, _, nx0, ny0 = ModelMachine0.DicoSMStacked["ModelShape"]

        _, _, nx1, ny1 = self.ModelShape
        dx = nx1 - nx0

        for iSource in range(SourceCat.shape[0]):
            x0 = SourceCat.X[iSource]
            y0 = SourceCat.Y[iSource]

            x1 = x0 + dx
            y1 = y0 + dx

            if not ((x1, y1) in self.DicoSMStacked["Comp"].keys()):
                self.DicoSMStacked["Comp"][(x1, y1)] = ModelMachine0.DicoSMStacked["Comp"][(x0, y0)]
            else:
                self.DicoSMStacked["Comp"][(x1, y1)] += ModelMachine0.DicoSMStacked["Comp"][(x0, y0)]
