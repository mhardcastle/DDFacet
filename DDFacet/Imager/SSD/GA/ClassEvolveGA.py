
import random

#from deap import base
from deap import base
from deap import creator
from deap import tools
import numpy
from DDFacet.Imager.SSD.GA import algorithms
import multiprocessing
from DDFacet.Array import NpShared

from DDFacet.ToolsDir import ModFFTW
import numpy as np
import os
#import Select

from DDFacet.Imager.SSD import ClassArrayMethodSSD

def FilterIslandsPix(ListIn,Npix):
    ListOut=[]
    for x,y in ListIn:
        Cx=((x>=0)&(x<Npix))
        Cy=((y>=0)&(y<Npix))
        if (Cx&Cy):
            ListOut.append([x,y])
    return ListOut


class ClassEvolveGA():
    def __init__(self,Dirty,PSF,FreqsInfo,ListPixData=None,ListPixParms=None,IslandBestIndiv=None,GD=None,
                 WeightFreqBands=None,PixVariance=1e-2,iFacet=0,iIsland=None,IdSharedMem="",
                 ParallelFitness=False):
        _,_,NPixPSF,_=PSF.shape
        if ListPixData is None:
            x,y=np.mgrid[0:NPixPSF:1,0:NPixPSF:1]
            ListPixData=np.array([x.ravel().tolist(),y.ravel().tolist()]).T.tolist()
        if ListPixParms is None:
            x,y=np.mgrid[0:NPixPSF:1,0:NPixPSF:1]
            ListPixParms=np.array([x.ravel().tolist(),y.ravel().tolist()]).T.tolist()
        self.IslandBestIndiv=IslandBestIndiv

        _,_,Npix,_=Dirty.shape
        ListPixData=FilterIslandsPix(ListPixData,Npix)
        ListPixParms=FilterIslandsPix(ListPixParms,Npix)
        

        self.IdSharedMem=IdSharedMem
        self.iIsland=iIsland
        self.ArrayMethodsMachine=ClassArrayMethodSSD.ClassArrayMethodSSD(Dirty,PSF,ListPixParms,ListPixData,FreqsInfo,
                                                                         PixVariance=PixVariance,
                                                                         iFacet=iFacet,
                                                                         IslandBestIndiv=IslandBestIndiv,
                                                                         GD=GD,
                                                                         WeightFreqBands=WeightFreqBands,
                                                                         iIsland=iIsland,
                                                                         IdSharedMem=IdSharedMem,
                                                                         ParallelFitness=ParallelFitness)
        self.InitEvolutionAlgo()
        #self.ArrayMethodsMachine.testMovePix()
        #stop

    def InitEvolutionAlgo(self):

        creator.create("FitnessMax", base.Fitness, weights=self.ArrayMethodsMachine.WeightsEA)
        creator.create("Individual", numpy.ndarray, fitness=creator.FitnessMax)

        toolbox = base.Toolbox()

        # Obj=[toolbox.attr_float_unif]*self.ArrayMethodsMachine.NParms
        # Obj=[toolbox.attr_float_unif]*self.ArrayMethodsMachine.NParms
        # Obj=[toolbox.attr_float_normal]*self.ArrayMethodsMachine.NParms

        Obj=self.ArrayMethodsMachine.PM.GiveInitList(toolbox)

        toolbox.register("individual", tools.initCycle, creator.Individual,
                         Obj, n=1)

        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        
        
        
        #toolbox.register("evaluate", self.ArrayMethodsMachine.GiveFitness)
        # toolbox.register("mate", tools.cxTwoPoint)
        toolbox.register("mate", tools.cxUniform, indpb=0.5)
        # toolbox.register("mate", tools.cxOrdered)
        # toolbox.register("mutate", tools.mutGaussian, indpb=0.3,  mu=0.0, sigma=.1)
        #toolbox.register("mutate", self.ArrayMethodsMachine.mutGaussian, pFlux=0.3, p0=0.3, pMove=0.3)
        self.MutConfig=pFlux,p0,pMove=0.2,0.5,0.2
        toolbox.register("mutate", self.ArrayMethodsMachine.mutGaussian, pFlux=0.2, p0=0.5, pMove=0.2)

        toolbox.register("select", tools.selTournament, tournsize=3)
        #toolbox.register("select", Select.selTolTournament, tournsize=3, Tol=4)

        #toolbox.register("select", tools.selRoulette)

        self.toolbox=toolbox



    def main(self,NGen=1000,NIndiv=100,DoPlot=True):
        #os.system("rm png/*.png")
        #random.seed(64)
        #np.random.seed(64)
        toolbox=self.toolbox
        # pool = multiprocessing.Pool(processes=6)
        # toolbox.register("map", pool.map)
        self.pop = toolbox.population(n=NIndiv)
        self.hof = tools.HallOfFame(1, similar=numpy.array_equal)
        #self.hof = tools.ParetoFront(1, similar=numpy.array_equal)

        # stats = tools.Statistics(lambda ind: ind.fitness.values)
        # stats.register("avg", numpy.mean)
        # stats.register("std", numpy.std)
        # stats.register("min", numpy.min)
        # stats.register("max", numpy.max)


        for indiv in self.pop:
            indiv.fill(0)

        #print "Best indiv start",
        #self.ArrayMethodsMachine.PM.PrintIndiv(self.IslandBestIndiv)

        if self.IslandBestIndiv is not None:
            SModelArray,Alpha=self.ArrayMethodsMachine.DeconvCLEAN()

            if np.max(np.abs(self.IslandBestIndiv))==0:
                self.ArrayMethodsMachine.PM.ReinitPop(self.pop,SModelArray)
            else:
                NIndiv=len(self.pop)/2
                pop0=self.pop[0:NIndiv]
                pop1=self.pop[NIndiv::]

                
                # self.ArrayMethodsMachine.PM.ReinitPop(pop0,SModelArray)

                # half with the best indiv
                SModelArrayBest=self.ArrayMethodsMachine.PM.ArrayToSubArray(self.IslandBestIndiv,"S")
                AlphaModel=None
                if "Alpha" in self.ArrayMethodsMachine.PM.SolveParam:
                    AlphaModel=self.ArrayMethodsMachine.PM.ArrayToSubArray(self.IslandBestIndiv,"Alpha")
                GSigModel=None
                if "GSig" in self.ArrayMethodsMachine.PM.SolveParam:
                    GSigModel=self.ArrayMethodsMachine.PM.ArrayToSubArray(self.IslandBestIndiv,"GSig")
                self.ArrayMethodsMachine.PM.ReinitPop(pop1,SModelArrayBest,AlphaModel=AlphaModel,GSigModel=GSigModel)

                # half of the pop with the MP model
                SModelArrayBest0=SModelArrayBest.copy()
                mask=(SModelArrayBest0==0)
                SModelArrayBest0[mask]=SModelArray[mask]
                self.ArrayMethodsMachine.PM.ReinitPop(pop0,SModelArrayBest0,AlphaModel=AlphaModel,GSigModel=GSigModel)

                self.pop=pop0+pop1


        # if self.IslandBestIndiv is not None:

        #     if np.max(np.abs(self.IslandBestIndiv))==0:
        #         #print "deconv"
        #         SModelArray,Alpha=self.ArrayMethodsMachine.DeconvCLEAN()

        #         #print "Estimated alpha",Alpha
        #         AlphaModel=np.zeros_like(SModelArray)+Alpha
        #         #AlphaModel[SModelArray==np.max(SModelArray)]=0

        #         self.ArrayMethodsMachine.PM.ReinitPop(self.pop,SModelArray)#,AlphaModel=AlphaModel)

        #         #print self.ArrayMethodsMachine.GiveFitness(self.pop[0],DoPlot=True)
        #         #stop
        #         #print self.pop
        #     else:
        #         SModelArray=self.ArrayMethodsMachine.PM.ArrayToSubArray(self.IslandBestIndiv,"S")
        #         AlphaModel=None
        #         if "Alpha" in self.ArrayMethodsMachine.PM.SolveParam:
        #             AlphaModel=self.ArrayMethodsMachine.PM.ArrayToSubArray(self.IslandBestIndiv,"Alpha")
                
        #         GSigModel=None
        #         if "GSig" in self.ArrayMethodsMachine.PM.SolveParam:
        #             GSigModel=self.ArrayMethodsMachine.PM.ArrayToSubArray(self.IslandBestIndiv,"GSig")
                
        #         self.ArrayMethodsMachine.PM.ReinitPop(self.pop,SModelArray,AlphaModel=AlphaModel,GSigModel=GSigModel)

        # set best Chi2
        _=self.ArrayMethodsMachine.GiveFitnessPop([self.IslandBestIndiv])



        self.pop, log= algorithms.eaSimple(self.pop, toolbox, cxpb=0.3, mutpb=0.5, ngen=NGen, 
                                           halloffame=self.hof, 
                                           #stats=stats,
                                           verbose=False, 
                                           ArrayMethodsMachine=self.ArrayMethodsMachine,
                                           DoPlot=DoPlot,
                                           MutConfig=self.MutConfig)
        self.ArrayMethodsMachine.KillWorkers()

        # #:param mu: The number of individuals to select for the next generation.
        # #:param lambda\_: The number of children to produce at each generation.
        # #:param cxpb: The probability that an offspring is produced by crossover.
        # #:param mutpb: The probability that an offspring is produced by mutation.

        # mu=70
        # lambda_=50
        # cxpb=0.3
        # mutpb=0.5
        # ngen=1000

        # self.pop, log= algorithms.eaMuPlusLambda(self.pop, toolbox, mu, lambda_, cxpb, mutpb, ngen,
        #                               stats=None, halloffame=None, verbose=__debug__,
        #                               ArrayMethodsMachine=self.ArrayMethodsMachine)

        V = tools.selBest(self.pop, 1)[0]

        #print "Best indiv end"
        #self.ArrayMethodsMachine.PM.PrintIndiv(V)
        
        # V.fill(0)
        # S=self.ArrayMethodsMachine.PM.ArrayToSubArray(V,"S")
        # G=self.ArrayMethodsMachine.PM.ArrayToSubArray(V,"GSig")
        
        # S[0]=1.
        # #S[1]=2.
        # G[0]=1.
        # #G[1]=2.

        # MA=self.ArrayMethodsMachine.PM.GiveModelArray(V)

        # # print "Sum best indiv",MA.sum(axis=1)
        # # print "Size indiv",V.size
        # # print "indiv",V
        # # print self.ArrayMethodsMachine.ListPixData
        # # print MA[0,:]

        NpShared.DelArray("%sPSF_Island_%4.4i"%(self.IdSharedMem,self.iIsland))

        return V
