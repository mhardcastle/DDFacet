#!/usr/bin/env python

from pyrap.tables import table
from pyrap.images import image
import pyfits
from Sky import ClassSM
import optparse
import numpy as np
import glob
import os
from Other import reformat
SaveFile="last_MyCasapy2BBS.obj"
import pickle
import scipy.ndimage
from Tools import ModFFTW
from SkyModel.PSourceExtract import ClassIslands
from SkyModel.Other.ClassCasaImage import PutDataInNewImage
import scipy.special
from DDFacet.Other import MyLogger
log=MyLogger.getLogger("MakeMask")
from SkyModel.Other.progressbar import ProgressBar
import collections
from SkyModel.Other.MyHist import MyCumulHist
from SkyModel.PSourceExtract import Gaussian
from SkyModel.Sky import ModRegFile

def read_options():
    desc=""" cyril.tasse@obspm.fr"""
    
    opt = optparse.OptionParser(usage='Usage: %prog --ms=somename.MS <options>',version='%prog version 1.0',description=desc)
    group = optparse.OptionGroup(opt, "* Data-related options")
    group.add_option('--RestoredIm',type="str",help="default is %default",default=None)
    group.add_option('--UseIslands',type="int",help="default is %default",default=0)
    group.add_option('--Th',type="float",default=10,help="default is %default")
    group.add_option("--Box",type="str",default="30,2",help="default is %default")
    group.add_option("--OutName",type="str",help="default is %default",default="mask")
    group.add_option("--OutNameNoiseMap",type="str",help="default is %default",default="")
    group.add_option("--ds9Mask",type="str",help="default is %default",default="")
    
    #group.add_option("--MedFilter",type="str",default="50,10")
    opt.add_option_group(group)

    
    options, arguments = opt.parse_args()

    f = open(SaveFile,"wb")
    pickle.dump(options,f)
    

            

#####################"

    


class ClassMakeMask():
    def __init__(self,FitsFile=None,
                 Th=5.,
                 Box=(50,10),
                 UseIslands=False,
                 OutName="mask",
                 ds9Mask="",
                 OutNameNoiseMap=""):

        self.ds9Mask=ds9Mask
        self.FitsFile=FitsFile
        self.Th=Th
        self.Box,self.IncrPix=Box
        self.Boost=self.IncrPix
        self.box=self.Box,self.Box
        self.CasaIm=image(self.FitsFile)
        self.Restored=self.CasaIm.getdata()
        self.UseIslands=UseIslands
        self.OutName=OutName
        self.OutNameNoiseMap=OutNameNoiseMap

        im=self.CasaIm
        c=im.coordinates()
        incr=np.abs(c.dict()["direction0"]["cdelt"][0])
        self.incr_rad=incr

        if self.UseIslands:
            PMaj=(im.imageinfo()["restoringbeam"]["major"]["value"])
            PMin=(im.imageinfo()["restoringbeam"]["minor"]["value"])
            PPA=(im.imageinfo()["restoringbeam"]["positionangle"]["value"])

            
            ToSig=(1./3600.)*(np.pi/180.)/(2.*np.sqrt(2.*np.log(2)))
            SigMaj_rad=PMaj*ToSig
            SigMin_rad=PMin*ToSig
            SixMaj_pix=SigMaj_rad/incr
            SixMin_pix=SigMin_rad/incr
            PPA_rad=PPA*np.pi/180

            x,y=np.mgrid[-10:11:1,-10:11:1]
            self.RefGauss=Gaussian.GaussianXY(x,y,1.,sig=(SixMin_pix,SixMaj_pix),pa=PPA_rad)
            self.RefGauss_xy=x,y
            
            self.BeamMin_pix=SixMin_pix*(2.*np.sqrt(2.*np.log(2)))
            self.BeamMaj_pix=SixMaj_pix*(2.*np.sqrt(2.*np.log(2)))
            self.RBeam_pix=SixMaj_pix
            print>>log, "Restoring Beam size of (%3.3f, %3.3f) pixels"%(self.BeamMin_pix, self.BeamMaj_pix)
        
        
        

        # #################"
        # _,_,nx,ny=self.Restored.shape
        # xc,yc=nx/2,nx/2
        # sup=200
        # x,y=np.mgrid[-sup:sup:1,-sup:sup:1]
        # G=Gaussian.GaussianXY(x,y,1.,sig=(7,18),pa=0.)
        # self.Restored[0,0,xc:xc+2*sup,yc:yc+2*sup]+=G[:,:]

        # xc,yc=nx/2+10,nx/2+10

        # G=Gaussian.GaussianXY(x,y,1.,sig=(3,3),pa=0.)
        # self.Restored[0,0,xc:xc+2*sup,yc:yc+2*sup]+=G[:,:]


        # #################"
        
        
        #self.Restored=np.load("testim.npy")
        self.A=self.Restored[0,0]

    def GiveVal(self,A,xin,yin):
        x,y=round(xin),round(yin)
        s=A.shape[0]-1
        cond=(x<0)|(x>s)|(y<0)|(y>s)
        if cond:
            value="out"
        else:
            value="%8.2f mJy"%(A.T[x,y]*1000.)
        return "x=%4i, y=%4i, value=%10s"%(x,y,value)

    def ComputeNoiseMap(self):
        print>>log, "Compute noise map..."
        Boost=self.Boost
        Acopy=self.Restored[0,0,0::Boost,0::Boost].copy()
        SBox=(self.box[0]/Boost,self.box[1]/Boost)


        # MeanAbs=scipy.ndimage.filters.mean_filter(np.abs(Acopy),SBox)
        # Acopy[Acopy>0]=MeanAbs[Acopy>0]
        # Noise=np.sqrt(scipy.ndimage.filters.median_filter(np.abs(Acopy)**2,SBox))

        x=np.linspace(-10,10,1000)
        f=0.5*(1.+scipy.special.erf(x/np.sqrt(2.)))
        n=SBox[0]*SBox[1]
        F=1.-(1.-f)**n
        ratio=np.abs(np.interp(0.5,F,x))

        Noise=-scipy.ndimage.filters.minimum_filter(Acopy,SBox)/ratio
        #Noise[Noise<0]=0

        # indxy=(Acopy>5.*Noise)
        # Acopy[indxy]=5*Noise[indxy]
        # Noise=np.sqrt(scipy.ndimage.filters.median_filter(np.abs(Acopy)**2,SBox))

        # indxy=(Acopy>5.*Noise)
        # Acopy[indxy]=5*Noise[indxy]
        # Noise=np.sqrt(scipy.ndimage.filters.median_filter(np.abs(Acopy)**2,SBox))

        NoiseMed=np.median(Noise)
        Noise[Noise<NoiseMed]=NoiseMed

        self.Noise=np.zeros_like(self.Restored[0,0])
        for i in range(Boost):
            for j in range(Boost):
                s00,s01=Noise.shape
                s10,s11=self.Noise[i::Boost,j::Boost].shape
                s0,s1=min(s00,s10),min(s10,s11)
                self.Noise[i::Boost,j::Boost][0:s0,0:s1]=Noise[:,:][0:s0,0:s1]
        ind=np.where(self.Noise==0.)
        self.Noise[ind]=1e-10

        if self.OutNameNoiseMap!="":
            #print>>log, "Save noise map as %s"%self.OutNameNoiseMap
            #self.CasaIm.saveas(self.OutNameNoiseMap)
            #CasaNoise=image(self.OutNameNoiseMap)
            #CasaNoise.putdata(self.Noise)
            #CasaNoise.tofits(self.OutNameNoiseMap+".fits")
            #del(CasaNoise)
            os.system("rm -rf %s"%self.OutNameNoiseMap)
            os.system("rm -rf %s"%self.OutNameNoiseMap+".fits")
            PutDataInNewImage(self.FitsFile,self.OutNameNoiseMap+".fits",np.float32(self.Noise))
    # def ComputeNoiseMap(self):
    #     print "Compute noise map..."
    #     Boost=self.Boost
    #     Acopy=self.Restored[0,0,0::Boost,0::Boost].copy()
    #     SBox=(self.box[0]/Boost,self.box[1]/Boost)
    #     Noise=np.sqrt(scipy.ndimage.filters.median_filter(np.abs(Acopy)**2,SBox))
    #     self.Noise=np.zeros_like(self.Restored[0,0])
    #     for i in range(Boost):
    #         for j in range(Boost):
    #             s00,s01=Noise.shape
    #             s10,s11=self.Noise[i::Boost,j::Boost].shape
    #             s0,s1=min(s00,s10),min(s10,s11)
    #             self.Noise[i::Boost,j::Boost][0:s0,0:s1]=Noise[:,:][0:s0,0:s1]
    #     print " ... done"
    #     ind=np.where(self.Noise==0.)
    #     self.Noise[ind]=1e-10

    def MakeMask(self):
        self.ImMask=(self.Restored[0,0,:,:]>self.Th*self.Noise)
        self.ImMask[:,-1]=0
        self.ImMask[:,0]=0
        self.ImMask[0,:]=0
        self.ImMask[-1,:]=0
        #self.ImIsland=scipy.ndimage.filters.median_filter(self.ImIsland,size=(3,3))


    def MaskSelectedDS9(self):
        ds9Mask=self.ds9Mask
        print>>log,"Reading ds9 region file: %s"%ds9Mask
        R=ModRegFile.RegToNp(ds9Mask)
        R.Read()
        
        IncludeCat=R.CatSel
        
        ExcludeCat=R.CatExclude
        
        print>>log,"  Excluding pixels"

        for iRegExclude in range(R.CatExclude.shape[0]):
            rac,decc,Radius=R.CatExclude.ra[iRegExclude],R.CatExclude.dec[iRegExclude],R.CatExclude.Radius[iRegExclude]
            RadiusPix=(1.1*Radius/self.incr_rad)
            freq,pol,_,_=self.CasaIm.toworld((0,0,0,0))

            _,_,yc,xc=self.CasaIm.topixel((freq,pol,decc,rac))

            xGrid,yGrid=np.mgrid[int(xc-RadiusPix):int(xc+RadiusPix)+1,int(yc-RadiusPix):int(yc+RadiusPix)+1]
            xGrid=xGrid.ravel()
            yGrid=yGrid.ravel()

            for iPix in range(xGrid.size):
                # if iPix%10000==0:
                #     print iPix,"/",xGrid.size
                ipix,jpix=xGrid[iPix],yGrid[iPix]
                _,_,dec,ra=self.CasaIm.toworld((0,0,jpix,ipix))
                #d=np.sqrt((ra-rac)**2+(dec-decc)**2)
                d=self.GiveAngDist(ra,dec,rac,decc)
                if d<Radius:
                    #print "zeros",ipix,jpix
                    self.ImMask[jpix,ipix]=0
        

        #self.ImMask.fill(0)
        print>>log,"  Including pixels"
        for iRegInclude in range(IncludeCat.shape[0]):
            rac,decc,Radius=IncludeCat.ra[iRegInclude],IncludeCat.dec[iRegInclude],IncludeCat.Radius[iRegInclude]
            RadiusPix=(1.1*Radius/self.incr_rad)
            freq,pol,_,_=self.CasaIm.toworld((0,0,0,0))

            _,_,yc,xc=self.CasaIm.topixel((freq,pol,decc,rac))
            
            xGrid,yGrid=np.mgrid[int(xc-RadiusPix):int(xc+RadiusPix)+1,int(yc-RadiusPix):int(yc+RadiusPix)+1]
            xGrid=xGrid.flatten().tolist()
            yGrid=yGrid.flatten().tolist()

            for ipix,jpix in zip(xGrid,yGrid):
                _,_,dec,ra=self.CasaIm.toworld((0,0,jpix,ipix))
                #d=np.sqrt((ra-rac)**2+(dec-decc)**2)
                d=self.GiveAngDist(ra,dec,rac,decc)
                #print ipix,jpix
                if d<Radius: 
                    #print "ones",ipix,jpix
                    self.ImMask[jpix,ipix]=1

    def GiveAngDist(self,ra1,dec1,ra2,dec2):
        sin=np.sin
        cos=np.cos
        #cosA = sin(dec1)*sin(dec2) + cos(dec1)*cos(dec1)*cos(ra1 - ra2) 
        #A=np.arccos(cosA)
        A=np.sqrt(((ra1-ra2)*cos((dec1+dec2)/2.))**2+(dec1-dec2)**2)
        return A

    def BuildIslandList(self):
        import scipy.ndimage

        print>>log,"  Labeling islands"
        self.ImIsland,NIslands=scipy.ndimage.label(self.ImMask)
        ImIsland=self.ImIsland
        NIslands+=1
        nx,_=ImIsland.shape

        print>>log,"  Found %i islands"%NIslands
        
        NMaxPix=100000
        Island=np.zeros((NIslands,NMaxPix,2),np.int32)
        NIslandNonZero=np.zeros((NIslands,),np.int32)

        print>>log,"  Extracting pixels in islands"
        pBAR= ProgressBar('white', width=50, block='=', empty=' ',Title="      Extracting ", HeaderSize=10,TitleSize=13)
        comment=''



        for ipix in range(nx):
            
            pBAR.render(int(100*ipix / (nx-1)), comment)
            for jpix in range(nx):
                iIsland=self.ImIsland[ipix,jpix]
                if iIsland:
                    NThis=NIslandNonZero[iIsland]
                    Island[iIsland,NThis,0]=ipix
                    Island[iIsland,NThis,1]=jpix
                    NIslandNonZero[iIsland]+=1

        print>>log,"  Listing pixels in islands"

        NMinPixIsland=5
        DicoIslands=collections.OrderedDict()
        for iIsland in range(1,NIslands):
            ind=np.where(Island[iIsland,:,0]!=0)[0]
            if ind.size < NMinPixIsland: continue
            Npix=ind.size
            Comps=np.zeros((Npix,3),np.float32)
            for ipix in range(Npix):
                x,y=Island[iIsland,ipix,0],Island[iIsland,ipix,1]
                s=self.Restored[0,0,x,y]
                Comps[ipix,0]=x
                Comps[ipix,1]=y
                Comps[ipix,2]=s
            DicoIslands[iIsland]=Comps

        print>>log,"  Final number of islands: %i"%len(DicoIslands)
        self.DicoIslands=DicoIslands
        

    def FilterIslands(self):
        DicoIslands=self.DicoIslands
        NIslands=len(self.DicoIslands)
        print>>log, "  Filter each individual islands"
        #pBAR= ProgressBar('white', width=50, block='=', empty=' ',Title="      Filter ", HeaderSize=10,TitleSize=13)
        #comment=''

        NormHist=True

        for iIsland in DicoIslands.keys():
            #pBAR.render(int(100*iIsland / float(len(DicoIslands.keys())-1)), comment)
            x,y,s=DicoIslands[iIsland].T
            #Im=self.GiveIm(x,y,s)
            #pylab.subplot(1,2,1)
            #pylab.imshow(Im,interpolation="nearest")
            # pylab.subplot(1,2,2)

            sr=self.RefGauss.copy()*np.max(s)

            xm,ym=int(np.mean(x)),int(np.mean(y))
            Th=self.Th*self.Noise[xm,ym]

            xg,yg=self.RefGauss_xy

            MaskSel=(sr>Th)
            xg_sel=xg[MaskSel].ravel()
            yg_sel=yg[MaskSel].ravel()
            sr_sel=sr[MaskSel].ravel()
            if sr_sel.size<7: continue

            ###############
            logs=s*s.size#np.log10(s*s.size)
            X,Y=MyCumulHist(logs,Norm=NormHist)
            logsr=sr_sel*sr_sel.size#np.log10(sr_sel*sr_sel.size)
            Xr,Yr=MyCumulHist(logsr,Norm=NormHist)
            Cut=0.9
            ThisTh=np.interp(Cut,Yr,Xr)
            #ThisTh=(ThisTh)/sr_sel.size
            
            #Im=self.GiveIm(xg_sel,yg_sel,sr_sel)
            #pylab.subplot(1,2,2)
            #pylab.imshow(Im,interpolation="nearest")
            


            ind=np.where(s*s.size>ThisTh)[0]
            #print ThisTh,ind.size/float(s.size )
            DicoIslands[iIsland]=DicoIslands[iIsland][ind].copy()
        #     pylab.clf()
        #     pylab.plot(X,Y)
        #     pylab.plot([ThisTh,ThisTh],[0,1],color="black")
        #     pylab.plot(Xr,Yr,color="black",lw=2,ls="--")
        #     pylab.draw()
        #     pylab.show(False)
        #     pylab.pause(0.1)
        #     import time
        #     time.sleep(1)
        # stop

    # def FilterIslands2(self):
    #     DicoIslands=self.DicoIslands
    #     NIslands=len(self.DicoIslands)
    #     print>>log, "  Filter each individual islands"
    #     #pBAR= ProgressBar('white', width=50, block='=', empty=' ',Title="      Filter ", HeaderSize=10,TitleSize=13)
    #     #comment=''

    #     NormHist=False

    #     gamma=1.
    #     d0=1.
    #     for iIsland in [DicoIslands.keys()[0],DicoIslands.keys()[2]]:#DicoIslands.keys():
    #         #pBAR.render(int(100*iIsland / float(len(DicoIslands.keys())-1)), comment)
    #         x,y,s=DicoIslands[iIsland].T
    #         #Im=self.GiveIm(x,y,s)
    #         #pylab.subplot(1,2,1)
    #         #pylab.imshow(Im,interpolation="nearest")
    #         # pylab.subplot(1,2,2)

    #         #sr=self.RefGauss.copy()*np.max(s)

    #         xm,ym=int(np.mean(x)),int(np.mean(y))
    #         Th=self.Th*self.Noise[xm,ym]

    #         Np=x.size
    #         DMat=np.sqrt((x.reshape((Np,1))-x.reshape((1,Np)))**2+(y.reshape((Np,1))-y.reshape((1,Np)))**2)#/self.RBeam_pix
            
    #         C=s.reshape((Np,1))*(1./(d0+DMat))**gamma
    #         #C=1./(d0+DMat)**gamma

            
    #         #C-=np.diag(np.diag(C))
    #         #MaxVec=np.mean(C,axis=1)
    #         #ind=(MaxVec>s).ravel()

    #         MaxVec=np.sum(C,axis=1)#*s#/Th

    #         pylab.clf()

    #         for iPix in range(C.shape[0])[0::10]:
    #             X,Y=MyCumulHist(C[iPix],Norm=False)
    #             pylab.plot(X,Y,color="gray")

    #         ic=np.argmax(s)
    #         X,Y=MyCumulHist(C[ic],Norm=False)
    #         pylab.plot(X,Y,color="black",ls="--",lw=2)

    #         pylab.draw()
    #         pylab.show(False)
    #         pylab.pause(0.1)

    #     #     Im0=self.GiveIm(x,y,s)
    #     #     #Im1=self.GiveIm(x,y,MaxVec)
    #     #     MNorm=MaxVec/s
    #     #     Im1=self.GiveIm(x,y,MNorm)
    #     #     ImMask=self.GiveIm(x,y,(MaxVec>1.))

    #     #     pylab.clf()
    #     #     pylab.subplot(1,3,1)
    #     #     pylab.imshow(Im0,interpolation="nearest")
    #     #     pylab.colorbar()
    #     #     #pylab.title("Th = %f"%Th)
    #     #     pylab.subplot(1,3,2)
    #     #     pylab.imshow(Im1,interpolation="nearest",vmin=MNorm.min(),vmax=MNorm.max())
    #     #     pylab.colorbar()
    #     #     pylab.subplot(1,3,3)
    #     #     pylab.imshow(ImMask,interpolation="nearest")
    #     #     pylab.draw()
    #     #     pylab.show(False)
    #     #     pylab.pause(0.1)
    #     #     import time
    #     #     time.sleep(1)
            
            

    #     #     # xg,yg=self.RefGauss_xy

    #     #     # MaskSel=(sr>Th)
    #     #     # xg_sel=xg[MaskSel].ravel()
    #     #     # yg_sel=yg[MaskSel].ravel()
    #     #     # sr_sel=sr[MaskSel].ravel()
    #     #     # if sr_sel.size<7: continue

    #     #     #DicoIslands[iIsland]=DicoIslands[iIsland][ind].copy()
    #     # #     pylab.clf()
    #     # #     pylab.plot(X,Y)
    #     # #     pylab.plot([ThisTh,ThisTh],[0,1],color="black")
    #     # #     pylab.plot(Xr,Yr,color="black",lw=2,ls="--")
    #     # #     pylab.draw()
    #     # #     pylab.show(False)
    #     # #     pylab.pause(0.1)
    #     # #     import time
    #     # #     time.sleep(1)
    #     stop


    def IslandsToMask(self):
        self.ImMask.fill(0)
        DicoIslands=self.DicoIslands
        NIslands=len(self.DicoIslands)
        print>>log, "  Building mask image from filtered islands"
        #pBAR= ProgressBar('white', width=50, block='=', empty=' ',Title="      Building ", HeaderSize=10,TitleSize=13)
        #comment=''
        for iIsland in DicoIslands.keys():
            #pBAR.render(int(100*iIsland / float(len(DicoIslands.keys())-1)), comment)
            x,y,s=DicoIslands[iIsland].T
            self.ImMask[np.int32(x),np.int32(y)]=1


    def GiveIm(self,x,y,s):
        dx=np.int32(x-x.min())
        dy=np.int32(y-y.min())
        nx=dx.max()+1
        ny=dy.max()+1
        print nx,ny
        Im=np.zeros((nx,ny),np.float32)
        Im[dx,dy]=s
        return Im

    def CreateMask(self):
        self.ComputeNoiseMap()
        self.MakeMask()

        if self.ds9Mask!="":
            self.MaskSelectedDS9()
        if self.UseIslands:
            # Make island list
            self.BuildIslandList()
            self.FilterIslands()
            self.IslandsToMask()

        #self.plot()
        nx,ny=self.ImMask.shape
        ImWrite=self.ImMask.reshape((1,1,nx,ny))
        
        PutDataInNewImage(self.FitsFile,self.FitsFile+"."+self.OutName,np.float32(ImWrite))

    def plot(self):
        import pylab
        pylab.clf()
        ax1=pylab.subplot(2,3,1)
        vmin,vmax=-np.max(self.Noise),5*np.max(self.Noise)
        MaxRms=np.max(self.Noise)
        ax1.imshow(self.A,vmin=vmin,vmax=vmax,interpolation="nearest",cmap="gray",origin="lower")
        ax1.format_coord = lambda x,y : self.GiveVal(self.A,x,y)
        pylab.title("Image")

        ax2=pylab.subplot(2,3,3,sharex=ax1,sharey=ax1)
        pylab.imshow(self.Noise,vmin=0.,vmax=np.max(self.Noise),interpolation="nearest",cmap="gray",origin="lower")
        ax2.format_coord = lambda x,y : self.GiveVal(self.Noise,x,y)
        pylab.title("Noise Image")
        pylab.xlim(0,self.A.shape[0]-1)
        pylab.ylim(0,self.A.shape[0]-1)


        ax3=pylab.subplot(2,3,6,sharex=ax1,sharey=ax1)
        ax3.imshow(self.ImMask,vmin=vmin,vmax=vmax,interpolation="nearest",cmap="gray",origin="lower")
        ax3.format_coord = lambda x,y : self.GiveVal(self.ImMask,x,y)
        pylab.title("Island Image")
        pylab.xlim(0,self.A.shape[0]-1)
        pylab.ylim(0,self.A.shape[0]-1)

        pylab.draw()
        pylab.show(False)

def main(options=None):
    
    if options==None:
        f = open(SaveFile,'rb')
        options = pickle.load(f)

    s0,s1=options.Box.split(",")
    Box=(int(s0),int(s1))
        
    MaskMachine=ClassMakeMask(options.RestoredIm,
                              Th=options.Th,
                              Box=Box,
                              UseIslands=options.UseIslands,
                              OutName=options.OutName,
                              ds9Mask=options.ds9Mask,
                              OutNameNoiseMap=options.OutNameNoiseMap)
    MaskMachine.CreateMask()

if __name__=="__main__":
    read_options()
    f = open(SaveFile,'rb')
    options = pickle.load(f)
    main(options=options)

def test():
    FitsFile="/media/tasse/data/DDFacet/Test/MultiFreqs3.restored.fits"
    Conv=ClassMakeMask(FitsFile=FitsFile,Th=5.,Box=(50,10))
    Conv.ComputeNoiseMap()
    Conv.FindIslands()

    nx,ny=Conv.ImIsland.shape
    ImWrite=Conv.ImIsland.reshape((1,1,nx,ny))

    PutDataInNewImage(FitsFile,FitsFile+".mask",np.float32(ImWrite))

    #Conv.plot()

    # import pylab
    # pylab.clf()
    # ax=pylab.subplot(1,2,1)
    # pylab.imshow(Conv.Restored[0,0],cmap="gray")
    # pylab.subplot(1,2,2,sharex=ax,sharey=ax)
    # pylab.imshow(Conv.IslandsMachine.ImIsland,cmap="gray")
    # pylab.draw()
    # pylab.show(False)
    # stop
