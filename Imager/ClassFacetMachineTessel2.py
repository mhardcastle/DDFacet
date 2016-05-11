import numpy as np
from DDFacet.Imager import ClassFacetMachine
from DDFacet.Other.progressbar import ProgressBar
import multiprocessing
import ClassDDEGridMachine
import numpy as np
import pylab
import ClassCasaImage
import pyfftw
from DDFacet.ToolsDir import ModCoord
from DDFacet.Other import MyPickle
import time
from DDFacet.Other import ModColor
from DDFacet.Array import NpShared
from DDFacet.ToolsDir import ModFFTW
import pyfftw
from scipy.spatial import Voronoi
from SkyModel.Sky import ModVoronoi
from DDFacet.Other import reformat
import os
from DDFacet.Other import MyLogger
log=MyLogger.getLogger("ClassFacetMachineTessel")
MyLogger.setSilent("MyLogger")
from DDFacet.ToolsDir.ModToolBox import EstimateNpix
from DDFacet.ToolsDir.GiveEdges import GiveEdges
from DDFacet.Imager.ClassImToGrid import ClassImToGrid
from matplotlib.path import Path
from SkyModel.Sky.ClassClusterKMean import ClassClusterKMean
from SkyModel.Sky import ModVoronoiToReg
import time
import Polygon
from DDFacet.ToolsDir import rad2hmsdms
from scipy.spatial import ConvexHull
from DDFacet.Gridder import _pyGridderSmearPols as _pyGridderSmear

class ClassFacetMachineTessel(ClassFacetMachine.ClassFacetMachine):

    def __init__(self,*args,**kwargs):
        ClassFacetMachine.ClassFacetMachine.__init__(self,*args,**kwargs)
        
    def appendMainField(self,Npix=512,Cell=10.,NFacets=5,
                        Support=11,OverS=5,Padding=1.2,
                        wmax=10000,Nw=11,RaDecRad=(0.,0.),
                        ImageName="Facet.image",**kw):
        

        Cell=self.GD["ImagerMainFacet"]["Cell"]

        self.ImageName=ImageName
        if self.DoPSF:
            Npix*=1

        MS=self.VS.MS
        self.LraFacet=[]
        self.LdecFacet=[]
        
        
        ChanFreq=self.VS.MS.ChanFreq.flatten()
        self.ChanFreq=ChanFreq
        
        self.NFacets = NFacets
        self.Cell=Cell
        self.CellSizeRad=(Cell/3600.)*np.pi/180.
        rac,decc=MS.radec
        self.MainRaDec=(rac,decc)
        self.nch=self.GD["MultiFreqs"]["NFreqBands"]
        self.NChanGrid=self.nch
        self.SumWeights=np.zeros((self.NChanGrid,self.npol),float)

        self.CoordMachine=ModCoord.ClassCoordConv(rac,decc)
        # self.setFacetsLocsSquare()
        self.setFacetsLocsTessel()


    def setFacetsLocsTessel(self):
        NFacets = self.NFacets
        Npix=self.GD["ImagerMainFacet"]["Npix"]
        Padding=self.GD["ImagerMainFacet"]["Padding"]
        self.Padding=Padding
        Npix,_=EstimateNpix(float(Npix),Padding=1)
        self.Npix=Npix
        self.OutImShape=(self.nch,self.npol,self.Npix,self.Npix)    

        RadiusTot=self.CellSizeRad*self.Npix/2
        self.RadiusTot=RadiusTot


        # Finding main image bounds
        # Np=100000
        # X=(np.random.rand(Np)*2-1.)*RadiusTot
        # Y=(np.random.rand(Np)*2-1.)*RadiusTot
        # XY = np.dstack((X, Y))
        # XY_flat = XY.reshape((-1, 2))
        lMainCenter,mMainCenter=0.,0.
        self.lmMainCenter=lMainCenter,mMainCenter
        self.CornersImageTot=np.array([[lMainCenter-RadiusTot,mMainCenter-RadiusTot],
                                       [lMainCenter+RadiusTot,mMainCenter-RadiusTot],
                                       [lMainCenter+RadiusTot,mMainCenter+RadiusTot],
                                       [lMainCenter-RadiusTot,mMainCenter+RadiusTot]])

        

        MSName=self.GD["VisData"]["MSName"]
        if ".txt" in MSName:
            f=open(MSName)
            Ls=f.readlines()
            f.close()
            MSName=[]
            for l in Ls:
                ll=l.replace("\n","")
                MSName.append(ll)
            MSName=MSName[0]

        
        SolsFile=self.GD["DDESolutions"]["DDSols"]
        if type(SolsFile)==list:
            SolsFile=self.GD["DDESolutions"]["DDSols"][0]

        if (SolsFile!="")&(not(".npz" in SolsFile)):
            Method=SolsFile
            ThisMSName=reformat.reformat(os.path.abspath(MSName),LastSlash=False)
            SolsFile="%s/killMS.%s.sols.npz"%(ThisMSName,Method)


        if SolsFile!="":
            ClusterNodes=np.load(SolsFile)["ClusterCat"]
            ClusterNodes=ClusterNodes.view(np.recarray)
            raNode=ClusterNodes.ra
            decNode=ClusterNodes.dec
            lFacet,mFacet=self.CoordMachine.radec2lm(raNode,decNode)
        else:
            CellSizeRad=(self.GD["ImagerMainFacet"]["Cell"]/3600.)*np.pi/180
            lrad=Npix*CellSizeRad*0.5


            NpixFacet=Npix/NFacets
            lfacet=NpixFacet*CellSizeRad*0.5
            lcenter_max=lrad-lfacet
            
            lFacet,mFacet,=np.mgrid[-lcenter_max:lcenter_max:(NFacets)*1j,-lcenter_max:lcenter_max:(NFacets)*1j]
            lFacet=lFacet.flatten()
            mFacet=mFacet.flatten()
            # ClusterNodes=np.load("BOOTES24_SB100-109.2ch8s.ms/killMS.KAFCA.sols.npz")["ClusterCat"]
            # ClusterNodes=ClusterNodes.view(np.recarray)
            # raNode=ClusterNodes.ra
            # decNode=ClusterNodes.dec
            # lFacet,mFacet=self.CoordMachine.radec2lm(raNode,decNode)
        self.lmSols=lFacet.copy(),mFacet.copy()

        raSols,decSols=self.CoordMachine.lm2radec(lFacet.copy(),mFacet.copy())
        self.radecSols=raSols,decSols


        #ClusterNodes=np.load("/data/tasse/BOOTES/BOOTES24_SB100-109.2ch8s.ms/killMS.KAFCA.sols.npz")["ClusterCat"]
        
        NodesCat=np.zeros((raSols.size,),dtype=[('ra',np.float),('dec',np.float),
                                                   ('l',np.float),('m',np.float)])
        NodesCat=NodesCat.view(np.recarray)
        NodesCat.ra=raSols
        NodesCat.dec=decSols
        NodesCat.l=lFacet
        NodesCat.m=mFacet
        NodeFile="%s.NodesCat.npy"%self.GD["Images"]["ImageName"]
        print>>log,"Saving Nodes catalog in %s"%NodeFile
        np.save(NodeFile,NodesCat)

        self.DicoImager={}
        
        xy=np.zeros((lFacet.size,2),np.float32)
        xy[:,0]=lFacet
        xy[:,1]=mFacet

        regFile="%s.tessel0.reg"%self.ImageName
        NFacets=self.NFacets=lFacet.size
        rac,decc=self.MainRaDec
        VM=ModVoronoiToReg.VoronoiToReg(rac,decc)
        if NFacets>2:
            vor = Voronoi(xy,furthest_site=False)
            regions, vertices = ModVoronoi.voronoi_finite_polygons_2d(vor,radius=1.)

            # points=xy
            # pylab.clf()
            # for region in regions:
            #     polygon = vertices[region]
            #     pylab.fill(*zip(*polygon), alpha=0.4)
            #     pylab.plot(points[:,0], points[:,1], 'ko')
            #     pylab.draw()
            #     pylab.show(False)

            # stop

            PP=Polygon.Polygon(self.CornersImageTot)

            LPolygon=[np.array(PP & Polygon.Polygon(np.array(vertices[region])))[0] for region in regions]



        elif NFacets==1:
            l0,m0=lFacet[0],mFacet[0]
            LPolygon=[self.CornersImageTot]
        #VM.ToReg(regFile,lFacet,mFacet,radius=.1)
        
        for iFacet,polygon0 in zip(range(len(LPolygon)),LPolygon):
            #polygon0 = vertices[region]
            P=polygon0.tolist()
            
        #VM.PolygonToReg(regFile,LPolygon,radius=0.1,Col="red")

        # stop





        ###########################################
        # SubDivide
        def GiveDiam(polygon):
            lPoly,mPoly=polygon.T
            l0=np.max([lMainCenter-RadiusTot,lPoly.min()])
            l1=np.min([lMainCenter+RadiusTot,lPoly.max()])
            m0=np.max([mMainCenter-RadiusTot,mPoly.min()])
            m1=np.min([mMainCenter+RadiusTot,mPoly.max()])
            dl=l1-l0
            dm=m1-m0
            diam=np.max([dl,dm])
            return diam,(l0,l1,m0,m1)

        DiamMax=self.GD["ImagerMainFacet"]["DiamMaxFacet"]*np.pi/180
        #DiamMax=4.5*np.pi/180
        DiamMin=self.GD["ImagerMainFacet"]["DiamMinFacet"]*np.pi/180
        
        def ClosePolygon(polygon):
            P=polygon.tolist()
            polygon=np.array(P+[P[0]])
            return polygon

        def GiveSubDivideRegions(polygonFacet,DMax):

            polygonFOV=self.CornersImageTot
            #polygonFOV=ClosePolygon(polygonFOV)
            PFOV=Polygon.Polygon(polygonFOV)

            #polygonFacet=ClosePolygon(polygonFacet)
            P0=Polygon.Polygon(polygonFacet)
            P0Cut=Polygon.Polygon(P0&PFOV)

            if P0Cut.nPoints()==0: return []

            polygonFacetCut=np.array(P0Cut[0])
            #polygonFacetCut=ClosePolygon(polygonFacetCut)

            diam,(l0,l1,m0,m1)=GiveDiam(polygonFacetCut)
            if diam<DMax: return [polygonFacetCut]

            Nl=int((l1-l0)/DMax)+1
            Nm=int((m1-m0)/DMax)+1
            dl=(l1-l0)/Nl
            dm=(m1-m0)/Nm
            lEdge=np.linspace(l0,l1,Nl+1)
            mEdge=np.linspace(m0,m1,Nm+1)
            lc=(lEdge[0:-1]+lEdge[1::])/2
            mc=(mEdge[0:-1]+mEdge[1::])/2
            LPoly=[]
            Lc,Mc=np.meshgrid(lc,mc)
            Lc=Lc.ravel().tolist()
            Mc=Mc.ravel().tolist()
            

            DpolySquare=np.array([[-dl,-dm],[dl,-dm],[dl,dm],[-dl,dm]])*0.5
            for lc,mc in zip(Lc,Mc):
                polySquare=DpolySquare.copy()#ClosePolygon(DpolySquare.copy())
                polySquare[:,0]+=lc
                polySquare[:,1]+=mc
                #polySquare=ClosePolygon(polySquare)
                P1=Polygon.Polygon(polySquare)

                POut=(P0Cut&P1)
                if POut.nPoints()==0: continue

                polyOut=np.array(POut[0])
                #polyOut=ClosePolygon(polyOut)
                LPoly.append(polyOut)

                # pylab.clf()
                # x,y=polygonFacetCut.T
                # pylab.plot(x,y,color="blue")
                # x,y=polygonFacet.T
                # pylab.plot(x,y,color="blue",ls=":",lw=3)
                # x,y=np.array(PFOV[0]).T
                # pylab.plot(x,y,color="black")
                # x,y=polySquare.T
                # pylab.plot(x,y,color="green",ls=":",lw=3)
                # x,y=polyOut.T
                # pylab.plot(x,y,color="red",ls="--",lw=3)
                # pylab.xlim(-0.03,0.03)
                # pylab.ylim(-0.03,0.03)
                # pylab.draw()
                # pylab.show(False)
                # pylab.pause(0.5)

            
            return LPoly
                
        def PlotPolygon(P,*args,**kwargs):
            for poly in P:
                x,y=ClosePolygon(np.array(poly)).T
                pylab.plot(x,y,*args,**kwargs)

        LPolygonNew=[]
        
        for iFacet in range(len(LPolygon)):
            polygon=LPolygon[iFacet]
            ThisDiamMax=DiamMax
            SubReg=GiveSubDivideRegions(polygon,ThisDiamMax)

            LPolygonNew+=SubReg

        regFile="%s.FacetMachine.tessel.ReCut.reg"%self.ImageName
        #VM.PolygonToReg(regFile,LPolygonNew,radius=0.1,Col="green",labels=[str(i) for i in range(len(LPolygonNew))])


        DicoPolygon={}
        for iFacet in range(len(LPolygonNew)): 
            DicoPolygon[iFacet]={}
            poly=LPolygonNew[iFacet]
            DicoPolygon[iFacet]["poly"]=poly
            diam,(l0,l1,m0,m1)=GiveDiam(poly)
            DicoPolygon[iFacet]["diam"]=diam
            DicoPolygon[iFacet]["diamMin"]=np.min([(l1-l0),(m1-m0)])
            xc,yc=np.mean(poly[:,0]),np.mean(poly[:,1])
            DicoPolygon[iFacet]["xyc"]=xc,yc
            dSol=np.sqrt((xc-lFacet)**2+(yc-mFacet)**2)
            DicoPolygon[iFacet]["iSol"]=np.where(dSol==np.min(dSol))[0]



        for iFacet in sorted(DicoPolygon.keys()):
            diam=DicoPolygon[iFacet]["diamMin"]
            # print iFacet,diam,DiamMin
            if diam<DiamMin:
                dmin=1e6
                xc0,yc0=DicoPolygon[iFacet]["xyc"]
                HasClosest=False
                for iFacetOther in sorted(DicoPolygon.keys()):
                    if iFacetOther==iFacet: continue
                    iSolOther=DicoPolygon[iFacetOther]["iSol"]
                    # print "  ",iSolOther,DicoPolygon[iFacet]["iSol"]
                    if iSolOther!=DicoPolygon[iFacet]["iSol"]:
                        continue
                    xc,yc=DicoPolygon[iFacetOther]["xyc"]
                    d=np.sqrt((xc-xc0)**2+(yc-yc0)**2)
                    if d<dmin:
                        dmin=d
                        iFacetClosest=iFacetOther
                        HasClosest=True
                if (HasClosest):
                    print>>log, "Merging facet #%i to #%i"%(iFacet,iFacetClosest)
                    P0=Polygon.Polygon(DicoPolygon[iFacet]["poly"])
                    P1=Polygon.Polygon(DicoPolygon[iFacetClosest]["poly"])
                    P2=(P0|P1)
                    POut=[]
                    for iP in range(len(P2)):
                        POut+=P2[iP]
                
                    poly=np.array(POut)
                    hull = ConvexHull(poly)
                    Contour=np.array([hull.points[hull.vertices,0],hull. points[hull.vertices,1]])
                    poly2=Contour.T
                    # poly2=hull.points
                    # pylab.clf()
                    # x,y=poly.T
                    # pylab.plot(x,y)
                    # x,y=poly2.T
                    # pylab.plot(x,y)
                    # # PlotPolygon(P0)
                    # # PlotPolygon(P1)
                    # # #PlotPolygon(P2,color="black")
                    # # x,y=poly2.T
                    # # PlotPolygon(x,y,color="black")
                    # pylab.draw()
                    # pylab.show()
                    # time.sleep(0.5)
                    
                    #poly2=np.array(P2[0])
                    del(DicoPolygon[iFacet])
                    DicoPolygon[iFacetClosest]["poly"]=poly2
                    DicoPolygon[iFacetClosest]["diam"]=GiveDiam(poly2)[0]
                    DicoPolygon[iFacetClosest]["xyc"]=np.mean(poly2[:,0]),np.mean(poly2[:,1])

        #stop
        LPolygonNew=[]
        for iFacet in sorted(DicoPolygon.keys()):
            LPolygonNew.append(DicoPolygon[iFacet]["poly"])

        
        # for iFacet in range(len(regions)):
        #     polygon=LPolygon[iFacet]
        #     ThisDiamMax=DiamMax
        #     while True:
        #         SubReg=GiveSubDivideRegions(polygon,ThisDiamMax)
        #         if SubReg==[]:
        #             break
        #         Diams=[GiveDiam(poly)[0] for poly in SubReg]
                
        #         if np.min(Diams)>DiamMin: break
        #         ThisDiamMax*=1.1
        #     LPolygonNew+=SubReg
        #     print 

        

        regFile="%s.tessel.reg"%self.GD["Images"]["ImageName"]
        #labels=["[F%i.C%i]"%(i,DicoPolygon[i]["iSol"]) for i in range(len(LPolygonNew))]
        #VM.PolygonToReg(regFile,LPolygonNew,radius=0.1,Col="green",labels=labels)

        VM.PolygonToReg(regFile,LPolygonNew,radius=0.1,Col="green")

        # pylab.clf()
        # x,y=LPolygonNew[11].T
        # pylab.plot(x,y)
        # pylab.draw()
        # pylab.show()
        # stop
        ###########################################

        NFacets=len(LPolygonNew)

        self.FacetCat=np.zeros((NFacets,),dtype=[('Name','|S200'),('ra',np.float),('dec',np.float),('SumI',np.float),
                                                     ("Cluster",int),
                                                     ("l",np.float),("m",np.float),
                                                     ("I",np.float)])
        self.FacetCat=self.FacetCat.view(np.recarray)
        self.FacetCat.I=1
        self.FacetCat.SumI=1
        print>>log,"Sizes (%i facets):"%(self.FacetCat.shape[0])
        print>>log,"   - Main field :   [%i x %i] pix"%(self.Npix,self.Npix)


        l_m_Diam=np.zeros((NFacets,4),np.float32)
        l_m_Diam[:,3]=np.arange(NFacets)

        D={}
        for iFacet in range(NFacets):
            D[iFacet]={}
            polygon=LPolygonNew[iFacet]
            D[iFacet]["Polygon"]=polygon
            lPoly,mPoly=polygon.T

            ThisDiam,(l0,l1,m0,m1)=GiveDiam(polygon)

            # ###############################
            # # Find barycenter of polygon
            # X=(np.random.rand(Np))*ThisDiam+l0
            # Y=(np.random.rand(Np))*ThisDiam+m0
            # XY = np.dstack((X, Y))
            # XY_flat = XY.reshape((-1, 2))
            # mpath = Path( polygon )
            # XY = np.dstack((X, Y))
            # XY_flat = XY.reshape((-1, 2))
            # mask_flat = mpath.contains_points(XY_flat)
            # mask=mask_flat.reshape(X.shape)
            # ###############################
            
            # lc=np.sum(X*mask)/np.sum(mask)
            # mc=np.sum(Y*mask)/np.sum(mask)
            # dl=np.max(np.abs(X[mask==1]-lc))
            # dm=np.max(np.abs(Y[mask==1]-mc))
            # diam=2*np.max([dl,dm])
            
            lc=(l0+l1)/2.
            mc=(m0+m1)/2.
            dl=l1-l0
            dm=m1-m0
            diam=np.max([dl,dm])

            l_m_Diam[iFacet,0]=lc
            l_m_Diam[iFacet,1]=mc
            l_m_Diam[iFacet,2]=diam

        self.SpacialWeigth={}
        self.DicoImager={} 
        indDiam=np.argsort(l_m_Diam[:,2])[::-1]
        l_m_Diam=l_m_Diam[indDiam]
                

        for iFacet in range(l_m_Diam.shape[0]):
            self.DicoImager[iFacet]={}
            self.DicoImager[iFacet]["Polygon"]=D[l_m_Diam[iFacet,3]]["Polygon"]
            x0=round(l_m_Diam[iFacet,0]/self.CellSizeRad)
            y0=round(l_m_Diam[iFacet,1]/self.CellSizeRad)
            if x0%2==0: x0+=1
            if y0%2==0: y0+=1
            l0=x0*self.CellSizeRad
            m0=y0*self.CellSizeRad
            diam=round(l_m_Diam[iFacet,2]/self.CellSizeRad)*self.CellSizeRad
            #self.AppendFacet(iFacet,l0,m0,diam)
            self.AppendFacet(iFacet,l0,m0,diam)





        #self.MakeMasksTessel()

        NpixMax=np.max([self.DicoImager[iFacet]["NpixFacet"] for iFacet in sorted(self.DicoImager.keys())])
        NpixMaxPadded=np.max([self.DicoImager[iFacet]["NpixFacetPadded"] for iFacet in sorted(self.DicoImager.keys())])
        self.PaddedGridShape=(1,1,NpixMaxPadded,NpixMaxPadded)
        self.FacetShape=(1,1,NpixMax,NpixMax)

        dmin=1
        for iFacet in range(len(self.DicoImager)):
            l,m=self.DicoImager[iFacet]["l0m0"]
            d=np.sqrt(l**2+m**2)
            if d<dmin:
                dmin=d
                iCentralFacet=iFacet
        self.iCentralFacet=iCentralFacet
        
        #regFile="%s.tessel.reg"%self.GD["Images"]["ImageName"]
        labels=[(self.DicoImager[i]["lmShift"][0],self.DicoImager[i]["lmShift"][1],"[F%i_S%i]"%(i,self.DicoImager[i]["iSol"])) for i in range(len(LPolygonNew))]
        VM.PolygonToReg(regFile,LPolygonNew,radius=0.1,Col="green",labels=labels)
        

        
        self.WriteCoordFacetFile()

        DicoName="%s.DicoFacet"%self.GD["Images"]["ImageName"]
        print>>log, "Saving DicoImager in %s"%DicoName
        MyPickle.Save(self.DicoImager,DicoName)

    def WriteCoordFacetFile(self):
        FacetCoordFile="%s.facetCoord.txt"%self.GD["Images"]["ImageName"]
        print>>log, "Writing facet coordinates in %s"%FacetCoordFile
        f = open(FacetCoordFile, 'w')
        ss="# (Name, Type, Ra, Dec, I, Q, U, V, ReferenceFrequency='7.38000e+07', SpectralIndex='[]', MajorAxis, MinorAxis, Orientation) = format"
        for iFacet in range(len(self.DicoImager)):
            ra,dec=self.DicoImager[iFacet]["RaDec"]
            sra =rad2hmsdms.rad2hmsdms(ra,Type="ra").replace(" ",":")
            sdec=rad2hmsdms.rad2hmsdms(dec).replace(" ",".")
            ss="%s, %s"%(sra,sdec)
            f.write(ss+'\n')
        f.close()


    def MakeMasksTessel(self):
        for iFacet in sorted(self.DicoImager.keys()):
            print>>log, "Making mask for facet %i"%iFacet
            Npix=self.DicoImager[iFacet]["NpixFacetPadded"]
            l0,l1,m0,m1=self.DicoImager[iFacet]["lmExtentPadded"]
            X, Y = np.mgrid[l0:l1:Npix*1j,m0:m1:Npix*1j]
            XY = np.dstack((X, Y))
            XY_flat = XY.reshape((-1, 2))
            vertices=self.DicoImager[iFacet]["Polygon"]
            mpath = Path( vertices ) # the vertices of the polygon
            mask_flat = mpath.contains_points(XY_flat)
            
            mask = mask_flat.reshape(X.shape)
            
            mpath = Path(self.CornersImageTot)
            mask_flat2 = mpath.contains_points(XY_flat)
            mask2 = mask_flat2.reshape(X.shape)
            mask[mask2==0]=0
            
            GaussPars=(10,10,0)

            SpacialWeigth=np.float32(mask.reshape((1,1,Npix,Npix)))
            
            # import pylab
            # pylab.clf()
            # pylab.subplot(1,2,1)
            # pylab.imshow(SpacialWeigth.reshape((Npix,Npix)),vmin=0,vmax=1.1,cmap="gray")
            SpacialWeigth=ModFFTW.ConvolveGaussian(SpacialWeigth,CellSizeRad=1,GaussPars=[GaussPars])
            SpacialWeigth=SpacialWeigth.reshape((Npix,Npix))
            SpacialWeigth/=np.max(SpacialWeigth)
            # pylab.subplot(1,2,2)
            # pylab.imshow(SpacialWeigth,vmin=0,vmax=1.1,cmap="gray")
            # pylab.draw()
            # pylab.show()
            
            
            #SpacialWeigth[np.abs(SpacialWeigth)<1e-2]=0.
            

            self.SpacialWeigth[iFacet]=SpacialWeigth
        



    def AppendFacet(self,iFacet,l0,m0,diam):
        diam *= self.Oversize

        DicoConfigGM=None
        lmShift=(l0,m0)
        self.DicoImager[iFacet]["lmShift"]=lmShift
        #CellRad=(Cell/3600.)*np.pi/180.
        
        
        raFacet,decFacet=self.CoordMachine.lm2radec(np.array([lmShift[0]]),np.array([lmShift[1]]))

        NpixFacet,_=EstimateNpix(diam/self.CellSizeRad,Padding=1)
        _,NpixPaddedGrid=EstimateNpix(NpixFacet,Padding=self.Padding)

        diam=NpixFacet*self.CellSizeRad
        diamPadded=NpixPaddedGrid*self.CellSizeRad
        RadiusFacet=diam*0.5
        RadiusFacetPadded=diamPadded*0.5
        self.DicoImager[iFacet]["lmDiam"]=RadiusFacet
        self.DicoImager[iFacet]["CellSizeRad"]=self.CellSizeRad
        self.DicoImager[iFacet]["lmDiamPadded"]=RadiusFacetPadded
        self.DicoImager[iFacet]["RadiusFacet"]=RadiusFacet
        self.DicoImager[iFacet]["RadiusFacetPadded"]=RadiusFacetPadded
        self.DicoImager[iFacet]["lmExtent"]=l0-RadiusFacet,l0+RadiusFacet,m0-RadiusFacet,m0+RadiusFacet
        self.DicoImager[iFacet]["lmExtentPadded"]=l0-RadiusFacetPadded,l0+RadiusFacetPadded,m0-RadiusFacetPadded,m0+RadiusFacetPadded

        lSol,mSol=self.lmSols
        raSol,decSol=self.lmSols
        dSol=np.sqrt((l0-lSol)**2+(m0-mSol)**2)
        iSol=np.where(dSol==np.min(dSol))[0]
        self.DicoImager[iFacet]["lmSol"]=lSol[iSol],mSol[iSol]
        self.DicoImager[iFacet]["radecSol"]=raSol[iSol],decSol[iSol]
        self.DicoImager[iFacet]["iSol"]=iSol
        
        
        #print>>log,"#[%3.3i] %f, %f"%(iFacet,l0,m0)
        #print>>log,"   Delta %f, %f"%(l0-self.DicoImager[iFacet]["lmSol"][0],m0-self.DicoImager[iFacet]["lmSol"][1])
        DicoConfigGM={"Npix":NpixFacet,
                      "Cell":self.GD["ImagerMainFacet"]["Cell"],
                      "ChanFreq":self.ChanFreq,
                      "DoPSF":False,
                      "Support":self.GD["ImagerCF"]["Support"],
                      "OverS":self.GD["ImagerCF"]["OverS"],
                      "wmax":self.GD["ImagerCF"]["wmax"],
                      "Nw":self.GD["ImagerCF"]["Nw"],
                      "WProj":True,
                      "DoDDE":self.DoDDE,
                      "Padding":self.GD["ImagerMainFacet"]["Padding"]}



        _,_,NpixOutIm,NpixOutIm=self.OutImShape

        self.DicoImager[iFacet]["l0m0"]=lmShift#self.CoordMachine.radec2lm(raFacet,decFacet)
        self.DicoImager[iFacet]["RaDec"]=raFacet[0],decFacet[0]
        self.LraFacet.append(raFacet[0])
        self.LdecFacet.append(decFacet[0])
        xc,yc=int(round(l0/self.CellSizeRad+NpixOutIm/2)),int(round(m0/self.CellSizeRad+NpixOutIm/2))

        self.DicoImager[iFacet]["pixCentral"]=xc,yc
        self.DicoImager[iFacet]["pixExtent"]=round(xc-NpixFacet/2),round(xc+NpixFacet/2+1),round(yc-NpixFacet/2),round(yc+NpixFacet/2+1)
        self.DicoImager[iFacet]["NpixFacet"]=NpixFacet
        self.DicoImager[iFacet]["NpixFacetPadded"]=NpixPaddedGrid
        self.DicoImager[iFacet]["DicoConfigGM"]=DicoConfigGM
        self.DicoImager[iFacet]["IDFacet"]=iFacet
        #print self.DicoImager[iFacet]
        
        self.FacetCat.ra[iFacet]=raFacet[0]
        self.FacetCat.dec[iFacet]=decFacet[0]
        l,m=self.DicoImager[iFacet]["l0m0"]
        self.FacetCat.l[iFacet]=l
        self.FacetCat.m[iFacet]=m
        self.FacetCat.Cluster[iFacet]=iFacet



    def setFacetsLocsSquare(self):
        Npix=self.GD["ImagerMainFacet"]["Npix"]
        NFacets=self.GD["ImagerMainFacet"]["NFacets"]
        Padding=self.GD["ImagerMainFacet"]["Padding"]
        self.Padding=Padding
        NpixFacet,_=EstimateNpix(float(Npix)/NFacets,Padding=1)
        Npix=NpixFacet*NFacets
        self.Npix=Npix
        self.OutImShape=(self.nch,self.npol,self.Npix,self.Npix)    
        _,NpixPaddedGrid=EstimateNpix(NpixFacet,Padding=Padding)
        self.NpixPaddedFacet=NpixPaddedGrid
        self.NpixFacet=NpixFacet
        self.FacetShape=(self.nch,self.npol,NpixFacet,NpixFacet)
        self.PaddedGridShape=(self.NChanGrid,self.npol,NpixPaddedGrid,NpixPaddedGrid)
        

        print>>log,"Sizes (%i x %i facets):"%(NFacets,NFacets)
        print>>log,"   - Main field :   [%i x %i] pix"%(self.Npix,self.Npix)
        print>>log,"   - Each facet :   [%i x %i] pix"%(NpixFacet,NpixFacet)
        print>>log,"   - Padded-facet : [%i x %i] pix"%(NpixPaddedGrid,NpixPaddedGrid)

        

        ############################

        self.NFacets=NFacets
        lrad=Npix*self.CellSizeRad*0.5
        self.ImageExtent=[-lrad,lrad,-lrad,lrad]

        lfacet=NpixFacet*self.CellSizeRad*0.5
        lcenter_max=lrad-lfacet
        lFacet,mFacet,=np.mgrid[-lcenter_max:lcenter_max:(NFacets)*1j,-lcenter_max:lcenter_max:(NFacets)*1j]
        lFacet=lFacet.flatten()
        mFacet=mFacet.flatten()
        x0facet,y0facet=np.mgrid[0:Npix:NpixFacet,0:Npix:NpixFacet]
        x0facet=x0facet.flatten()
        y0facet=y0facet.flatten()

        #print "Append1"; self.IM.CI.E.clear()
        
        
        self.DicoImager={}
        for iFacet in range(lFacet.size):
            self.DicoImager[iFacet]={}





        #print "Append2"; self.IM.CI.E.clear()


        self.FacetCat=np.zeros((lFacet.size,),dtype=[('Name','|S200'),('ra',np.float),('dec',np.float),('SumI',np.float),
                                                     ("Cluster",int),
                                                     ("l",np.float),("m",np.float),
                                                     ("I",np.float)])
        self.FacetCat=self.FacetCat.view(np.recarray)
        self.FacetCat.I=1
        self.FacetCat.SumI=1

        
        for iFacet in range(lFacet.size):
            l0=x0facet[iFacet]*self.CellSizeRad
            m0=y0facet[iFacet]*self.CellSizeRad
            l0=lFacet[iFacet]
            m0=mFacet[iFacet]


            #print x0facet[iFacet],y0facet[iFacet],l0,m0
            self.AppendFacet(iFacet,l0,m0,NpixFacet*self.CellSizeRad)

        self.DicoImagerCentralFacet=self.DicoImager[lFacet.size/2]

        self.SetLogModeSubModules("Silent")
        self.MakeREG()

    #===========================================

    def ImToGrids(self,Image,ToGrid=False):
        Im2Grid=ClassImToGrid(OverS=self.GD["ImagerCF"]["OverS"],GD=self.GD)
        nch,npol=self.nch,self.npol
        ChanSel=sorted(list(set(self.VS.DicoMSChanMappingDegridding[self.VS.iCurrentMS].tolist())))

        self.ListFacetModel=[]
        self.ListFacetSumFlux=[]
        for iFacet in sorted(self.DicoImager.keys()):

            SharedMemName="%sSpheroidal.Facet_%3.3i"%(self.IdSharedMem,iFacet)
            SPhe=NpShared.GiveArray(SharedMemName)
            SpacialWeight=self.SpacialWeigth[iFacet]
            # Grid,_=Im2Grid.GiveGridTessel(Image,self.DicoImager,iFacet,self.NormImage,SPhe,SpacialWeight)
            # GridSharedMemName="%sModelGrid.Facet_%3.3i"%(self.IdSharedMem,iFacet)
            # NpShared.ToShared(GridSharedMemName,Grid)

            
            ModelFacet,SumFlux=Im2Grid.GiveModelTessel(Image,self.DicoImager,iFacet,self.NormImage,SPhe,SpacialWeight,ChanSel=ChanSel,ToGrid=ToGrid)
            
            ModelSharedMemName="%sModelImage.Facet_%3.3i"%(self.IdSharedMem,iFacet)
            
            ModelFacet=NpShared.ToShared(ModelSharedMemName,ModelFacet)
            self.ListFacetModel.append(ModelFacet)
            self.ListFacetSumFlux.append(SumFlux)

    def GiveVisParallel(self,times,uvwIn,visIn,flag,A0A1,ModelImage):
        NCPU=self.NCPU
        #visOut=np.zeros_like(visIn)


        print>>log, "Model image to facets ..."
        self.ImToGrids(ModelImage)

        NFacets=len(self.DicoImager.keys())
        # ListModelImage=[]
        # for iFacet in self.DicoImager.keys():
        #     ListModelImage.append(self.DicoImager[iFacet]["ModelFacet"])
        # NpShared.PackListArray("%sModelImage"%self.IdSharedMem,ListModelImage)
        # del(ListModelImage)
        # for iFacet in self.DicoImager.keys():
        #     del(self.DicoImager[iFacet]["ModelFacet"])

        print>>log, "    ... done"


        ListSemaphores=["%sSemaphore%3.3i"%(self.IdSharedMem,i) for i in range(5*self.NCPU)]
        _pyGridderSmear.pySetSemaphores(ListSemaphores)
        work_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()

        NJobs=NFacets
        for iFacet in range(NFacets):
            work_queue.put(iFacet)

        workerlist=[]
        for ii in range(NCPU):
            W=WorkerImager(work_queue, result_queue,
                           self.GD,
                           Mode="DeGrid",
                           FFTW_Wisdom=self.FFTW_Wisdom,
                           DicoImager=self.DicoImager,
                           IdSharedMem=self.IdSharedMem,
                           IdSharedMemData=self.IdSharedMemData,
                           ApplyCal=self.ApplyCal,
                           NFreqBands=self.GD["MultiFreqs"]["NFreqBands"],
                           ListSemaphores=ListSemaphores)

            workerlist.append(W)
            workerlist[ii].start()


        pBAR= ProgressBar('white', width=50, block='=', empty=' ',Title="DeGridding ", HeaderSize=10,TitleSize=13)
        # pBAR.disable()
        pBAR.render(0, '%4i/%i' % (0,NFacets))
        iResult=0
        while iResult < NJobs:
            DicoResult=result_queue.get()
            if DicoResult["Success"]:
                iResult+=1
            NDone=iResult
            intPercent=int(100*  NDone / float(NFacets))
            pBAR.render(intPercent, '%4i/%i' % (NDone,NFacets))



        for ii in range(NCPU):
            workerlist[ii].shutdown()
            workerlist[ii].terminate()
            workerlist[ii].join()

        NpShared.DelAll("%sModelGrid"%(self.IdSharedMemData))
        _pyGridderSmear.pyDeleteSemaphore(ListSemaphores)
            
        return True

    def CalcDirtyImagesParallel(self,times,uvwIn,visIn,flag,A0A1,W=None,doStack=True):#,Channel=0):
        
        
        NCPU=self.NCPU

        NFacets=len(self.DicoImager.keys())

        work_queue = multiprocessing.JoinableQueue()


        PSFMode=False
        if self.DoPSF:
            #visIn.fill(1)
            PSFMode=True

        NJobs=NFacets
        for iFacet in range(NFacets):
            work_queue.put(iFacet)

        workerlist=[]
        SpheNorm=True
        if self.ConstructMode=="Fader":
            SpheNorm=False

        List_Result_queue=[]
        for ii in range(NCPU):
            List_Result_queue.append(multiprocessing.JoinableQueue())


        for ii in range(NCPU):
            W=WorkerImager(work_queue, List_Result_queue[ii],
                           self.GD,
                           Mode="Grid",
                           FFTW_Wisdom=self.FFTW_Wisdom,
                           DicoImager=self.DicoImager,
                           IdSharedMem=self.IdSharedMem,
                           IdSharedMemData=self.IdSharedMemData,
                           ApplyCal=self.ApplyCal,
                           SpheNorm=SpheNorm,
                           PSFMode=PSFMode,
                           NFreqBands=self.GD["MultiFreqs"]["NFreqBands"])
            workerlist.append(W)
            workerlist[ii].start()

        pBAR= ProgressBar('white', width=50, block='=', empty=' ',Title="  Gridding ", HeaderSize=10,TitleSize=13)
#        pBAR.disable()
        pBAR.render(0, '%4i/%i' % (0,NFacets))
        iResult=0
        while iResult < NJobs:
            DicoResult=None
            for result_queue in List_Result_queue:
                if result_queue.qsize()!=0:
                    try:
                        DicoResult=result_queue.get_nowait()
                        break
                    except:
                        pass
                
            if DicoResult==None:
                time.sleep(1)
                continue


            if DicoResult["Success"]:
                iResult+=1
                NDone=iResult
                intPercent=int(100*  NDone / float(NFacets))
                pBAR.render(intPercent, '%4i/%i' % (NDone,NFacets))

            iFacet=DicoResult["iFacet"]

            self.DicoImager[iFacet]["SumWeights"]+=DicoResult["Weights"]
            self.DicoImager[iFacet]["SumJones"]+=DicoResult["SumJones"]
            #print self.DicoImager[iFacet]["SumJones"],DicoResult["SumJones"]
            self.DicoImager[iFacet]["SumJonesChan"][self.VS.iCurrentMS]+=DicoResult["SumJonesChan"]
            #print self.DicoImager[iFacet]["SumJonesChan"]
            # if iFacet==0:
            #     ThisSumWeights=DicoResult["Weights"]
            #     self.SumWeights+=ThisSumWeights

            DirtyName=DicoResult["DirtyName"]
            ThisDirty=NpShared.GiveArray(DirtyName)
            #print "minmax facet = %f %f"%(ThisDirty.min(),ThisDirty.max())


            if (doStack==True)&("Dirty" in self.DicoGridMachine[iFacet].keys()):
                self.DicoGridMachine[iFacet]["Dirty"]+=ThisDirty
            else:
                self.DicoGridMachine[iFacet]["Dirty"]=ThisDirty.copy()
            NpShared.DelArray(DirtyName)
            #NCH,_,_,_=ThisDirty.shape
            #print np.max(self.DicoGridMachine[iFacet]["Dirty"].reshape((NCH,ThisDirty.size/NCH)),axis=1)


        for ii in range(NCPU):
            workerlist[ii].shutdown()
            workerlist[ii].terminate()
            workerlist[ii].join()

        
        return True



    def InitParallel(self):

        

        NCPU=self.NCPU

        NFacets=len(self.DicoImager.keys())

        work_queue = multiprocessing.Queue()
        result_queue = multiprocessing.Queue()

        NJobs=NFacets
        for iFacet in range(NFacets):
            work_queue.put(iFacet)

        self.SpacialWeigth={}

        workerlist=[]
        for ii in range(NCPU):
            W=WorkerImager(work_queue, result_queue,
                           self.GD,
                           Mode="Init",
                           FFTW_Wisdom=self.FFTW_Wisdom,
                           DicoImager=self.DicoImager,
                           IdSharedMem=self.IdSharedMem,
                           IdSharedMemData=self.IdSharedMemData,
                           ApplyCal=self.ApplyCal,
                           CornersImageTot=self.CornersImageTot,
                           NFreqBands=self.GD["MultiFreqs"]["NFreqBands"])
            workerlist.append(W)
            
            workerlist[ii].start()

        #print>>log, ModColor.Str("  --- Initialising DDEGridMachines ---",col="green")
        pBAR= ProgressBar('white', width=50, block='=', empty=' ',Title="      Init W ", HeaderSize=10,TitleSize=13)
        pBAR.render(0, '%4i/%i' % (0,NFacets))
        iResult=0

        while iResult < NJobs:
            DicoResult=result_queue.get()
            if DicoResult["Success"]:
                iResult+=1
            NDone=iResult
            intPercent=int(100*  NDone / float(NFacets))
            pBAR.render(intPercent, '%4i/%i' % (NDone,NFacets))


        for ii in range(NCPU):
            workerlist[ii].shutdown()
            workerlist[ii].terminate()
            workerlist[ii].join()


        for iFacet in sorted(self.DicoImager.keys()):
            NameSpacialWeigth="%sSpacialWeigth.Facet_%3.3i"%(self.IdSharedMem,iFacet)
            SpacialWeigth=NpShared.GiveArray(NameSpacialWeigth)
            self.SpacialWeigth[iFacet]=SpacialWeigth
        return True

#===============================================
#===============================================
#===============================================
#===============================================

class WorkerImager(multiprocessing.Process):
    def __init__(self,
                 work_queue,
                 result_queue,
                 GD,
                 Mode="Init",
                 FFTW_Wisdom=None,
                 DicoImager=None,
                 IdSharedMem=None,
                 IdSharedMemData=None,
                 ApplyCal=False,
                 SpheNorm=True,
                 PSFMode=False,
                 CornersImageTot=None,NFreqBands=1,ListSemaphores=None):
        multiprocessing.Process.__init__(self)
        self.work_queue = work_queue
        self.result_queue = result_queue
        self.kill_received = False
        self.exit = multiprocessing.Event()
        self.Mode=Mode
        self.FFTW_Wisdom=FFTW_Wisdom
        self.GD=GD
        self.DicoImager=DicoImager
        self.IdSharedMem=IdSharedMem
        self.IdSharedMemData=IdSharedMemData
        self.Apply_killMS=(GD["DDESolutions"]["DDSols"]!="")&(GD["DDESolutions"]["DDSols"]!=None)
        self.Apply_Beam=(GD["Beam"]["BeamModel"]!=None)
        self.ApplyCal=(self.Apply_killMS)|(self.Apply_Beam)
        self.SpheNorm=SpheNorm
        self.PSFMode=PSFMode
        self.CornersImageTot=CornersImageTot
        self.NFreqBands=NFreqBands
        self.ListSemaphores=ListSemaphores

    def shutdown(self):
        self.exit.set()

    def GiveGM(self,iFacet):
        GridMachine=ClassDDEGridMachine.ClassDDEGridMachine(self.GD,#RaDec=self.DicoImager[iFacet]["RaDec"],
                                                            self.DicoImager[iFacet]["DicoConfigGM"]["ChanFreq"],
                                                            self.DicoImager[iFacet]["DicoConfigGM"]["Npix"],
                                                            lmShift=self.DicoImager[iFacet]["lmShift"],
                                                            IdSharedMem=self.IdSharedMem,
                                                            IdSharedMemData=self.IdSharedMemData,
                                                            IDFacet=iFacet,
                                                            SpheNorm=self.SpheNorm,
                                                            NFreqBands=self.NFreqBands,
                                                            ListSemaphores=self.ListSemaphores)
        

        return GridMachine
        
    def GiveDicoJonesMatrices(self):
        DicoJonesMatrices=None
        #if self.PSFMode:
        #    return None

        if self.ApplyCal:
            DicoJonesMatrices={}

        if self.Apply_killMS:
            DicoJones_killMS=NpShared.SharedToDico("%sJonesFile_killMS"%self.IdSharedMemData)
            DicoJonesMatrices["DicoJones_killMS"]=DicoJones_killMS
            DicoJonesMatrices["DicoJones_killMS"]["MapJones"]=NpShared.GiveArray("%sMapJones_killMS"%self.IdSharedMemData)
            DicoClusterDirs_killMS=NpShared.SharedToDico("%sDicoClusterDirs_killMS"%self.IdSharedMemData)
            DicoJonesMatrices["DicoJones_killMS"]["DicoClusterDirs"]=DicoClusterDirs_killMS
            DicoJonesMatrices["DicoJones_killMS"]["AlphaReg"]=NpShared.GiveArray("%sAlphaReg"%self.IdSharedMemData)

        if self.Apply_Beam:
            DicoJones_Beam=NpShared.SharedToDico("%sJonesFile_Beam"%self.IdSharedMemData)
            DicoJonesMatrices["DicoJones_Beam"]=DicoJones_Beam
            DicoJonesMatrices["DicoJones_Beam"]["MapJones"]=NpShared.GiveArray("%sMapJones_Beam"%self.IdSharedMemData)
            DicoClusterDirs_Beam=NpShared.SharedToDico("%sDicoClusterDirs_Beam"%self.IdSharedMemData)
            DicoJonesMatrices["DicoJones_Beam"]["DicoClusterDirs"]=DicoClusterDirs_Beam

        

        return DicoJonesMatrices

    def run(self):
        #print multiprocessing.current_process()
        while not self.kill_received:
            #gc.enable()
            try:
                iFacet = self.work_queue.get()
            except:
                break

            if self.FFTW_Wisdom!=None:
                pyfftw.import_wisdom(self.FFTW_Wisdom)


            if self.Mode=="Init":


                #print iFacet,self.DicoImager[iFacet]["pixExtent"]
                Npix=self.DicoImager[iFacet]["NpixFacetPadded"]
                l0,l1,m0,m1=self.DicoImager[iFacet]["lmExtentPadded"]
                X, Y = np.mgrid[l0:l1:Npix*1j,m0:m1:Npix*1j]
                XY = np.dstack((X, Y))
                XY_flat = XY.reshape((-1, 2))
                vertices=self.DicoImager[iFacet]["Polygon"]
                mpath = Path( vertices ) # the vertices of the polygon
                mask_flat = mpath.contains_points(XY_flat)
                
                mask = mask_flat.reshape(X.shape)
                
                mpath = Path(self.CornersImageTot)
                mask_flat2 = mpath.contains_points(XY_flat)
                mask2 = mask_flat2.reshape(X.shape)
                mask[mask2==0]=0
                
                GaussPars=(10,10,0)
                
                SpacialWeigth=np.float32(mask.reshape((1,1,Npix,Npix)))
                
                # import pylab
                # pylab.clf()
                # pylab.subplot(1,2,1)
                # pylab.imshow(SpacialWeigth.reshape((Npix,Npix)),vmin=0,vmax=1.1,cmap="gray")

                SpacialWeigth=ModFFTW.ConvolveGaussian(SpacialWeigth,CellSizeRad=1,GaussPars=[GaussPars])
                SpacialWeigth=SpacialWeigth.reshape((Npix,Npix))
                SpacialWeigth/=np.max(SpacialWeigth)

                # pylab.subplot(1,2,2)
                # pylab.imshow(SpacialWeigth,vmin=0,vmax=1.1,cmap="gray")
                # pylab.draw()
                # pylab.show()
                
                
                #SpacialWeigth[np.abs(SpacialWeigth)<1e-2]=0.
                #self.SpacialWeigth[iFacet]=SpacialWeigth
                NameSpacialWeigth="%sSpacialWeigth.Facet_%3.3i"%(self.IdSharedMem,iFacet)
                NpShared.ToShared(NameSpacialWeigth,SpacialWeigth)
                
                self.GiveGM(iFacet)

                self.result_queue.put({"Success":True,"iFacet":iFacet})
                
            elif self.Mode=="Grid":

                #import gc
                #gc.enable()
                GridMachine=self.GiveGM(iFacet)
                DATA=NpShared.SharedToDico("%sDicoData"%self.IdSharedMemData)
                uvwThis=DATA["uvw"]
                visThis=DATA["data"]
                flagsThis=DATA["flags"]
                times=DATA["times"]
                A0=DATA["A0"]
                A1=DATA["A1"]
                A0A1=A0,A1
                W=DATA["Weights"]
                freqs=DATA["freqs"]
                ChanMapping=DATA["ChanMapping"]

                DecorrMode=self.GD["DDESolutions"]["DecorrMode"]
                if ('F' in DecorrMode)|("T" in DecorrMode):
                    uvw_dt=DATA["uvw_dt"]
                    DT,Dnu=DATA["MSInfos"]
                    GridMachine.setDecorr(uvw_dt,DT,Dnu,SmearMode=DecorrMode)

                GridName="%sGridFacet.%3.3i"%(self.IdSharedMem,iFacet)
                Grid=NpShared.GiveArray(GridName)
                DicoJonesMatrices=self.GiveDicoJonesMatrices()
                Dirty=GridMachine.put(times,uvwThis,visThis,flagsThis,A0A1,W,
                                      DoNormWeights=False, 
                                      DicoJonesMatrices=DicoJonesMatrices,
                                      freqs=freqs,DoPSF=self.PSFMode,
                                      ChanMapping=ChanMapping)#,doStack=False)

                DirtyName="%sImageFacet.%3.3i"%(self.IdSharedMem,iFacet)
                _=NpShared.ToShared(DirtyName,Dirty)
                #del(Dirty)
                Sw=GridMachine.SumWeigths.copy()
                SumJones=GridMachine.SumJones.copy()
                SumJonesChan=GridMachine.SumJonesChan.copy()
                del(GridMachine)

                self.result_queue.put({"Success":True,"iFacet":iFacet,"DirtyName":DirtyName,"Weights":Sw,"SumJones":SumJones,"SumJonesChan":SumJonesChan})
                

                # gc.collect()
                # print "sleeping"
                # time.sleep(10)

                # self.result_queue.put({"Success":True})

            elif self.Mode=="DeGrid":
                
                GridMachine=self.GiveGM(iFacet)
                DATA=NpShared.SharedToDico("%sDicoData"%self.IdSharedMemData)
                uvwThis=DATA["uvw"]
                visThis=DATA["data"]
                #PredictedDataName="%s%s"%(self.IdSharedMem,"predicted_data")
                #visThis=NpShared.GiveArray(PredictedDataName)
                flagsThis=DATA["flags"]
                times=DATA["times"]
                A0=DATA["A0"]
                A1=DATA["A1"]
                A0A1=A0,A1
                W=DATA["Weights"]
                freqs=DATA["freqs"]
                ChanMapping=DATA["ChanMappingDegrid"]

                DicoJonesMatrices=self.GiveDicoJonesMatrices()
                #GridSharedMemName="%sModelGrid.Facet_%3.3i"%(self.IdSharedMem,iFacet)
                #ModelGrid = NpShared.GiveArray(GridSharedMemName)
                ModelSharedMemName="%sModelImage.Facet_%3.3i"%(self.IdSharedMem,iFacet)
                ModelGrid = NpShared.GiveArray(ModelSharedMemName)

                DecorrMode=self.GD["DDESolutions"]["DecorrMode"]
                if ('F' in DecorrMode)|("T" in DecorrMode):
                    uvw_dt=DATA["uvw_dt"]
                    DT,Dnu=DATA["MSInfos"]
                    GridMachine.setDecorr(uvw_dt,DT,Dnu,SmearMode=DecorrMode)

                vis=GridMachine.get(times,uvwThis,visThis,flagsThis,A0A1,ModelGrid,ImToGrid=False,DicoJonesMatrices=DicoJonesMatrices,freqs=freqs,TranformModelInput="FT",
                                      ChanMapping=ChanMapping)
                # V=visThis[:,:,0]
                # f=flagsThis[:,:,0]
                # V=V[f==0]
                # ind=np.where(np.abs(V)>0)
                # V=V[ind]
                # print "np.max tessel2",np.mean(np.abs(V)),np.median(np.abs(V)),np.max(V)

                self.result_queue.put({"Success":True,"iFacet":iFacet})
#            print "Done %i"%iFacet
