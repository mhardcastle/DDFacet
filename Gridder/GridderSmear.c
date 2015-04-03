/* A file to test imorting C modules for handling arrays to Python */
#include <Python.h>
#include <math.h>
#include <time.h>
#include "arrayobject.h"
#include "GridderSmear.h"
#include "complex.h"
#include <omp.h>

clock_t start;

void initTime(){start=clock();}

void timeit(char* Name){
  clock_t diff;
  diff = clock() - start;
  start=clock();
  float msec = diff * 1000 / CLOCKS_PER_SEC;
  printf("%s: %f\n",Name,msec);
}

/* double AppendTimeit(){ */
/*   clock_t diff; */
/*   diff = clock() - start; */
/*   double msec = diff * 1000000 / CLOCKS_PER_SEC; */
/*   return msec; */
/* } */

void AddTimeit(double *aTime){
  clock_t diff;
  diff = clock() - start;
  start=clock();
  (*aTime)+= diff ;//* 1000000 / CLOCKS_PER_SEC;
}



/* #### Globals #################################### */

/* ==== Set up the methods table ====================== */
static PyMethodDef _pyGridderSmear_testMethods[] = {
	{"pyGridderWPol", pyGridderWPol, METH_VARARGS},
	{"pyDeGridderWPol", pyDeGridderWPol, METH_VARARGS},
	{NULL, NULL}     /* Sentinel - marks the end of this structure */
};

/* ==== Initialize the C_test functions ====================== */
// Module name must be _C_arraytest in compile and linked 
void init_pyGridderSmear()  {
  (void) Py_InitModule("_pyGridderSmear", _pyGridderSmear_testMethods);
  import_array();  // Must be present for NumPy.  Called first after above line.
}











static PyObject *pyGridderWPol(PyObject *self, PyObject *args)
{
  PyObject *ObjGridIn;
  PyArrayObject *np_grid, *vis, *uvw, *cfs, *flags, *weights, *sumwt, *increment, *freqs,*WInfos,*SmearMapping;

  PyObject *Lcfs;
  PyObject *LJones,*Lmaps;
  PyObject *LcfsConj;
  int dopsf;

  if (!PyArg_ParseTuple(args, "OO!O!O!O!O!iO!O!O!O!O!O!O!O!", 
			&ObjGridIn,
			&PyArray_Type,  &vis, 
			&PyArray_Type,  &uvw, 
			&PyArray_Type,  &flags, 
			&PyArray_Type,  &weights,
			&PyArray_Type,  &sumwt, 
			&dopsf, 
			&PyList_Type, &Lcfs,
			&PyList_Type, &LcfsConj,
			&PyArray_Type,  &WInfos,
			&PyArray_Type,  &increment,
			&PyArray_Type,  &freqs,
			&PyList_Type, &Lmaps,
			&PyList_Type, &LJones,
			&PyArray_Type,  &SmearMapping
			))  return NULL;
  int nx,ny,nz,nzz;
  np_grid = (PyArrayObject *) PyArray_ContiguousFromObject(ObjGridIn, PyArray_COMPLEX64, 0, 4);

  gridderWPol(np_grid, vis, uvw, flags, weights, sumwt, dopsf, Lcfs, LcfsConj, WInfos, increment, freqs, Lmaps, LJones, SmearMapping);
  
  return PyArray_Return(np_grid);

}


//////////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////////



//////////////////////////////////////////////////////////////////////
//////////////////////////////////////////////////////////////////////

void GiveJones(float complex *ptrJonesMatrices, int *JonesDims, float *ptrCoefs, int i_t, int i_ant0, int i_dir, int Mode, float complex *Jout){
  int nd_Jones,na_Jones,nch_Jones;
  nd_Jones=JonesDims[1];
  na_Jones=JonesDims[2];
  nch_Jones=JonesDims[3];
  
  int ipol,idir;
  if(Mode==0){
    int offJ0=i_t*nd_Jones*na_Jones*nch_Jones*4
      +i_dir*na_Jones*nch_Jones*4
      +i_ant0*nch_Jones*4;
    for(ipol=0; ipol<4; ipol++){
      Jout[ipol]=*(ptrJonesMatrices+offJ0+ipol);
    }
  }

  if(Mode==1){
    for(idir=0; idir<nd_Jones; idir++){
      int offJ0=i_t*nd_Jones*na_Jones*nch_Jones*4
	+idir*na_Jones*nch_Jones*4
	+i_ant0*nch_Jones*4;
      for(ipol=0; ipol<4; ipol++){
	Jout[ipol]+=ptrCoefs[idir]*(*(ptrJonesMatrices+offJ0+ipol));
	
	//printf("%i, %f, %f, %f\n",ipol,ptrCoefs[idir],creal(Jout[ipol]),cimag(Jout[ipol]));
      }
      
    }
  }
}




void gridderWPol(PyArrayObject *grid,
	      PyArrayObject *vis,
	      PyArrayObject *uvw,
	      PyArrayObject *flags,
	      PyArrayObject *weights,
	      PyArrayObject *sumwt,
	      int dopsf,
	      PyObject *Lcfs,
	      PyObject *LcfsConj,
	      PyArrayObject *Winfos,
	      PyArrayObject *increment,
		 PyArrayObject *freqs,
		 PyObject *Lmaps, 
		 PyObject *LJones,
	      PyArrayObject *SmearMapping
		 )
  {
    // Get size of convolution functions.
    int nrows     = uvw->dimensions[0];
    PyArrayObject *cfs;
    PyArrayObject *NpPolMap;
    NpPolMap = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(Lmaps, 0), PyArray_INT32, 0, 4);

    PyArrayObject *NpFacetInfos;
    NpFacetInfos = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(Lmaps, 1), PyArray_FLOAT64, 0, 4);


    ////////////////////////////////////////////////////////////////////////////
    ////////////////////////////////////////////////////////////////////////////
    ////////////////////////////////////////////////////////////////////////////
    int LengthJonesList=PyList_Size(LJones);
    int DoApplyJones=0;
    PyArrayObject *npJonesMatrices, *npTimeMappingJonesMatrices, *npA0, *npA1, *npJonesIDIR, *npCoefsInterp,*npModeInterpolation;
    float complex* ptrJonesMatrices;
    int *ptrTimeMappingJonesMatrices,*ptrA0,*ptrA1,*ptrJonesIDIR;
    float *ptrCoefsInterp;
    int i_dir;
    int nd_Jones,na_Jones,nch_Jones,nt_Jones;

    //    printf("len %i",LengthJonesList);
    int JonesDims[4];
    int ModeInterpolation=1;
    int *ptrModeInterpolation;
    int ApplyAmp,ApplyPhase,DoScaleJones;
    float CalibError,CalibError2;
    if(LengthJonesList>0){
      DoApplyJones=1;

      npTimeMappingJonesMatrices  = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 0), PyArray_INT32, 0, 4);
      ptrTimeMappingJonesMatrices = p_int32(npTimeMappingJonesMatrices);

      npA0 = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 1), PyArray_INT32, 0, 4);
      ptrA0 = p_int32(npA0);
      int ifor;
      


      npA1= (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 2), PyArray_INT32, 0, 4);
      ptrA1=p_int32(npA1);
 
      
      // (nt,nd,na,1,2,2)
      npJonesMatrices = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 3), PyArray_COMPLEX64, 0, 6);
      ptrJonesMatrices=p_complex64(npJonesMatrices);
      nt_Jones=(int)npJonesMatrices->dimensions[0];
      nd_Jones=(int)npJonesMatrices->dimensions[1];
      na_Jones=(int)npJonesMatrices->dimensions[2];
      nch_Jones=(int)npJonesMatrices->dimensions[3];
      JonesDims[0]=nt_Jones;
      JonesDims[1]=nd_Jones;
      JonesDims[2]=na_Jones;
      JonesDims[3]=nch_Jones;

      npJonesIDIR= (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 4), PyArray_INT32, 0, 4);
      ptrJonesIDIR=p_int32(npJonesIDIR);
      i_dir=ptrJonesIDIR[0];

      npCoefsInterp= (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 5), PyArray_FLOAT32, 0, 4);
      ptrCoefsInterp=p_float32(npCoefsInterp);

      npModeInterpolation= (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 6), PyArray_INT32, 0, 4);
      ptrModeInterpolation=p_int32(npModeInterpolation);
      ModeInterpolation=ptrModeInterpolation[0];

      PyObject *_FApplyAmp  = PyList_GetItem(LJones, 7);
      ApplyAmp=(int) PyFloat_AsDouble(_FApplyAmp);
      PyObject *_FApplyPhase  = PyList_GetItem(LJones, 8);
      ApplyPhase=(int) PyFloat_AsDouble(_FApplyPhase);

      PyObject *_FDoScaleJones  = PyList_GetItem(LJones, 9);
      DoScaleJones=(int) PyFloat_AsDouble(_FDoScaleJones);
      PyObject *_FCalibError  = PyList_GetItem(LJones, 10);
      CalibError=(float) PyFloat_AsDouble(_FCalibError);
      CalibError2=CalibError*CalibError;



    };
    ////////////////////////////////////////////////////////////////////////////
    ////////////////////////////////////////////////////////////////////////////
    ////////////////////////////////////////////////////////////////////////////
    
    double* ptrFacetInfos=p_float64(NpFacetInfos);
    double Cu=ptrFacetInfos[0];
    double Cv=ptrFacetInfos[1];
    double l0=ptrFacetInfos[2];
    double m0=ptrFacetInfos[3];
    double n0=sqrt(1-l0*l0-m0*m0)-1;


    double VarTimeGrid=0;
    int Nop=0;

    int npolsMap=NpPolMap->dimensions[0];
    int* PolMap=I_ptr(NpPolMap);
    
    //    printf("npols=%i %i\n",npolsMap,PolMap[3]);

    // Get size of grid.
    double* ptrWinfo = p_float64(Winfos);
    double WaveRefWave = ptrWinfo[0];
    double wmax = ptrWinfo[1];
    double NwPlanes = ptrWinfo[2];
    int OverS=floor(ptrWinfo[3]);


    //    printf("WaveRef=%f, wmax=%f \n",WaveRefWave,wmax);
    int nGridX    = grid->dimensions[3];
    int nGridY    = grid->dimensions[2];
    int nGridPol  = grid->dimensions[1];
    int nGridChan = grid->dimensions[0];

    // Get visibility data size.
    int nVisPol   = flags->dimensions[2];
    int nVisChan  = flags->dimensions[1];
    //    printf("(nrows, nVisChan, nVisPol)=(%i, %i, %i)\n",nrows,nVisChan,nVisPol);


    // Get oversampling and support size.
    int sampx = OverS;//int (cfs.sampling[0]);
    int sampy = OverS;//int (cfs.sampling[1]);

    double* __restrict__ sumWtPtr = p_float64(sumwt);//->data;
    double complex psfValues[4];
    psfValues[0] = psfValues[1] = psfValues[2] = psfValues[3] = 1;

    //uint inxRowWCorr(0);

    double offset_p[2],uvwScale_p[2];

    offset_p[0]=nGridX/2;//(nGridX-1)/2.;
    offset_p[1]=nGridY/2;
    float fnGridX=nGridX;
    float fnGridY=nGridY;
    double *incr=p_float64(increment);
    double *Pfreqs=p_float64(freqs);
    uvwScale_p[0]=fnGridX*incr[0];
    uvwScale_p[1]=fnGridX*incr[1];
    //printf("uvscale=(%f %f)\n",uvwScale_p[0],uvwScale_p[1]);
    double C=2.99792458e8;
    int inx;
    // Loop over all visibility rows to process.

    float complex J0[4]={0},J1[4]={0},J0inv[4]={0},J1H[4]={0},J1Hinv[4]={0},JJ[4]={0};
    double WaveLengthMean=0.;
    int visChan;
    for (visChan=0; visChan<nVisChan; ++visChan){
      WaveLengthMean+=C/Pfreqs[visChan];
    }
    WaveLengthMean/=nVisChan;

    //PyArrayObject *npMappingBlock=(PyArrayObject *) PyArray_ContiguousFromObject(SmearMapping, PyArray_INT32, 0, 4);
    int *MappingBlock = p_int32(SmearMapping);
    int NTotBlocks=MappingBlock[0];
    int *NRowBlocks=MappingBlock+1;
    int *StartRow=MappingBlock+1+NTotBlocks;

    int iBlock;

    double TimeShift[1]={0.};
    double TimeApplyJones[1]={0.};
    double TimeJones[1]={0.};
    double TimeGrid[1]={0.};
    double TimeGetJones[1]={0.};
    double TimeStuff[1]={0.};

    for(iBlock=0; iBlock<NTotBlocks; iBlock++){
    //for(iBlock=3507; iBlock<3508; iBlock++){
      int NRowThisBlock=NRowBlocks[iBlock]-2;
      int indexMap=StartRow[iBlock];
      int chStart=MappingBlock[indexMap];
      int chEnd=MappingBlock[indexMap+1];
      int *Row=MappingBlock+StartRow[iBlock]+2;

      float complex Vis[4]={0};
      float Umean=0;
      float Vmean=0;
      float Wmean=0;
      float FreqMean=0;
      int NVisThisblock=0;
      //printf("\n");
      //printf("Block[%i] Nrows=%i %i>%i\n",iBlock,NRowThisBlock,chStart,chEnd);

      double ThisWeight=0.;
      for (inx=0; inx<NRowThisBlock; inx++) {
	int irow = Row[inx];
	if(irow>nrows){continue;}
	double*  __restrict__ uvwPtr   = p_float64(uvw) + irow*3;
	double*   imgWtPtr = p_float64(weights) + irow  * nVisChan;
	//printf("[%i] %i>%i bl=(%i-%i)\n",irow,chStart,chEnd,ptrA0[irow],ptrA1[irow]);
	//printf("  row=[%i] %i>%i \n",irow,chStart,chEnd);
	
	//initTime();
	if(DoApplyJones){
	  int i_t=ptrTimeMappingJonesMatrices[irow];
	  int i_ant0=ptrA0[irow];
	  int i_ant1=ptrA1[irow];
	  GiveJones(ptrJonesMatrices, JonesDims, ptrCoefsInterp, i_t, i_ant0, i_dir, ModeInterpolation, J0);
	  GiveJones(ptrJonesMatrices, JonesDims, ptrCoefsInterp, i_t, i_ant1, i_dir, ModeInterpolation, J1);
	  NormJones(J0, ApplyAmp, ApplyPhase, DoScaleJones, uvwPtr, WaveLengthMean, CalibError);
	  NormJones(J1, ApplyAmp, ApplyPhase, DoScaleJones, uvwPtr, WaveLengthMean, CalibError);
	  MatInv(J0,J0inv,0);
	  MatH(J1,J1H);
	  MatInv(J1H,J1Hinv,0);
	} //endif DoApplyJones

	//AddTimeit(TimeGetJones);

	int ThisPol;
	for (visChan=chStart; visChan<chEnd; ++visChan) {
	  int doff = (irow * nVisChan + visChan) * nVisPol;
	  bool* __restrict__ flagPtr = p_bool(flags) + doff;
	  int OneFlagged=0;
	  int cond;
	  //char ch="a";
	  for(ThisPol =0; ThisPol<4;ThisPol++){
	    //cond=(flagPtr[ThisPol]==1);
	    //printf("  F[%i]: %i \n",ThisPol,cond);
	    if(flagPtr[ThisPol]==1){OneFlagged=1;}
	  }
	  if(OneFlagged){continue;}
	  
	  //AddTimeit(TimeStuff);
	  //###################### Facetting #######################
	  // Change coordinate and shift visibility to facet center
	  double ThisWaveLength=C/Pfreqs[visChan];
	  double complex UVNorm=2.*I*PI/ThisWaveLength;
	  double U=uvwPtr[0];
	  double V=uvwPtr[1];
	  double W=uvwPtr[2];
	  float complex corr=cexp(-UVNorm*(U*l0+V*m0+W*n0));
	  //AddTimeit(TimeShift);
	  //#######################################################

	  float complex* __restrict__ visPtr_Uncorr  = p_complex64(vis)  + doff;
	  float complex visPtr[4];
	  if(DoApplyJones){
	    MatDot(J0inv,visPtr_Uncorr,visPtr);
	    MatDot(visPtr,J1Hinv,visPtr);
	    for(ThisPol =0; ThisPol<4;ThisPol++){
	      Vis[ThisPol]+=visPtr[ThisPol]*(corr*(*imgWtPtr));
	    }
	  }else{
	    for(ThisPol =0; ThisPol<4;ThisPol++){
	      Vis[ThisPol]+=visPtr_Uncorr[ThisPol]*(corr*(*imgWtPtr));
	    }
	  };

	  //AddTimeit(TimeApplyJones);

	  U+=W*Cu;
	  V+=W*Cv;
	  //###################### Averaging #######################
	  Umean+=U;
	  Vmean+=V;
	  Wmean+=W;
	  FreqMean+=(float)Pfreqs[visChan];
	  ThisWeight+=*imgWtPtr;
	  NVisThisblock+=1;
	  //printf("      [%i,%i], fmean=%f %f\n",inx,visChan,(FreqMean/1e6),Pfreqs[visChan]);
	  
	}//endfor vischan
      }//endfor RowThisBlock
      if(NVisThisblock==0){continue;}
      Umean/=NVisThisblock;
      Vmean/=NVisThisblock;
      Wmean/=NVisThisblock;
      FreqMean/=NVisThisblock;

      //printf("  iblock: %i [%i], (uvw)=(%f, %f, %f) fmean=%f\n",iBlock,NVisThisblock,Umean,Vmean,Wmean,(FreqMean/1e6));
      /* int ThisPol; */
      /* for(ThisPol =0; ThisPol<4;ThisPol++){ */
      /* 	printf("   vis: %i (%f, %f)\n",ThisPol,creal(Vis[ThisPol]),cimag(Vis[ThisPol])); */
      /* } */
      
      initTime();
      // ################################################
      // ############## Start Gridding visibility #######
      int gridChan = 0;//chanMap_p[visChan];
      int CFChan = 0;//ChanCFMap[visChan];
      double recipWvl = FreqMean / C;
      double ThisWaveLength=C/FreqMean;

      // ############## W-projection ####################
      double wcoord=Wmean;
      int iwplane = floor((NwPlanes-1)*abs(wcoord)*(WaveRefWave/ThisWaveLength)/wmax+0.5);
      int skipW=0;
      if(iwplane>NwPlanes-1){skipW=1;continue;};
      
      if(wcoord>0){
      	cfs=(PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(Lcfs, iwplane), PyArray_COMPLEX64, 0, 2);
      } else{
      	cfs=(PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LcfsConj, iwplane), PyArray_COMPLEX64, 0, 2);
      }
      int nConvX = cfs->dimensions[0];
      int nConvY = cfs->dimensions[1];
      int supx = (nConvX/OverS-1)/2;
      int supy = (nConvY/OverS-1)/2;
      int SupportCF=nConvX/OverS;
      // ################################################


	
	

      if (gridChan >= 0  &&  gridChan < nGridChan) {
      	double posx,posy;
      	//For Even/Odd take the -1 off
      	posx = uvwScale_p[0] * Umean * recipWvl + offset_p[0];//#-1;
      	posy = uvwScale_p[1] * Vmean * recipWvl + offset_p[1];//-1;
	
      	int locx = nint (posx);    // location in grid
      	int locy = nint (posy);
      	//printf("locx=%i, locy=%i\n",locx,locy);
      	double diffx = locx - posx;
      	double diffy = locy - posy;
      	//printf("diffx=%f, diffy=%f\n",diffx,diffy);
	
      	int offx = nint (diffx * sampx); // location in
      	int offy = nint (diffy * sampy); // oversampling
      	//printf("offx=%i, offy=%i\n",offx,offy);
      	offx += (nConvX-1)/2;
      	offy += (nConvY-1)/2;
      	// Scaling with frequency is not necessary (according to Cyril).
      	double freqFact = 1;
      	int fsampx = nint (sampx * freqFact);
      	int fsampy = nint (sampy * freqFact);
      	int fsupx  = nint (supx / freqFact);
      	int fsupy  = nint (supy / freqFact);
	
      	// Only use visibility point if the full support is within grid.
	
      	//printf("offx=%i, offy=%i\n",offx,offy);
      	//assert(1==0);
	
      	if (locx-supx >= 0  &&  locx+supx < nGridX  &&
      	    locy-supy >= 0  &&  locy+supy < nGridY) {
	  
      	  int ipol;
      	  for (ipol=0; ipol<nVisPol; ++ipol) {
      	    float complex VisVal;
      	    if (dopsf==1) {
      	      VisVal = 1.;
      	    }else{
      	      VisVal =Vis[ipol];
      	    }
      	    //VisVal*=ThisWeight;

      	    // Map to grid polarization. Only use pol if needed.
      	    int gridPol = PolMap[ipol];
      	    if (gridPol >= 0  &&  gridPol < nGridPol) {
      	      int goff = (gridChan*nGridPol + gridPol) * nGridX * nGridY;
      	      int sy;
      	      float complex* __restrict__ gridPtr;
      	      const float complex* __restrict__ cf0;
      	      int io=(offy - fsupy*fsampy);
      	      int jo=(offx - fsupx*fsampx);
      	      int cfoff = io * OverS * SupportCF*SupportCF + jo * SupportCF*SupportCF;
      	      cf0 =  p_complex64(cfs) + cfoff;
      	      for (sy=-fsupy; sy<=fsupy; ++sy) {
      		gridPtr =  p_complex64(grid) + goff + (locy+sy)*nGridX + locx-supx;
      		int sx;
      		for (sx=-fsupx; sx<=fsupx; ++sx) {
      		  //printf("gird=(%f,%f), vis=(%f,%f), cf=(%f,%f)\n",creal((*gridPtr)),cimag((*gridPtr)),creal(VisVal),cimag(VisVal),creal(*cf0),cimag(*cf0));
      		  *gridPtr++ += VisVal * *cf0;
      		  cf0 ++;
      		}
		
      	      }
      	      sumWtPtr[gridPol+gridChan*nGridPol] += ThisWeight;
      	    } // end if gridPol
      	  } // end for ipol
      	} // end if ongrid
      } // end if gridChan
      //AddTimeit(TimeGrid);
 
    } //end for Block
    
    printf("Times:\n");
    printf("TimeShift:      %f\n",*TimeShift);
    printf("TimeApplyJones: %f\n",*TimeApplyJones);
    printf("TimeJones:      %f\n",*TimeJones);
    printf("TimeGrid:       %f\n",*TimeGrid);
    printf("TimeGetJones:   %f\n",*TimeGetJones);
    printf("TimeStuff:      %f\n",*TimeStuff);
  } // end 





////////////////////

static PyObject *pyDeGridderWPol(PyObject *self, PyObject *args)
{
  PyObject *ObjGridIn;
  PyObject *ObjVis;
  PyArrayObject *np_grid, *np_vis, *uvw, *cfs, *flags, *sumwt, *increment, *freqs,*WInfos,*SmearMapping;

  PyObject *Lcfs;
  PyObject *Lmaps,*LJones;
  PyObject *LcfsConj;
  int dopsf;

  if (!PyArg_ParseTuple(args, "O!OO!O!O!iO!O!O!O!O!O!O!O!", 
			//&ObjGridIn,
			&PyArray_Type,  &np_grid,
			&ObjVis,//&PyArray_Type,  &vis, 
			&PyArray_Type,  &uvw, 
			&PyArray_Type,  &flags, 
			//&PyArray_Type,  &rows, 
			&PyArray_Type,  &sumwt, 
			&dopsf, 
			&PyList_Type, &Lcfs,
			&PyList_Type, &LcfsConj,
			&PyArray_Type,  &WInfos,
			&PyArray_Type,  &increment,
			&PyArray_Type,  &freqs,
			&PyList_Type, &Lmaps, &PyList_Type, &LJones,
			&PyArray_Type, &SmearMapping
			))  return NULL;
  int nx,ny,nz,nzz;

  np_vis = (PyArrayObject *) PyArray_ContiguousFromObject(ObjVis, PyArray_COMPLEX64, 0, 3);

  

  DeGridderWPol(np_grid, np_vis, uvw, flags, sumwt, dopsf, Lcfs, LcfsConj, WInfos, increment, freqs, Lmaps, LJones, SmearMapping);
  
  return PyArray_Return(np_vis);

  //return Py_None;

}





void DeGridderWPol(PyArrayObject *grid,
		   PyArrayObject *vis,
		   PyArrayObject *uvw,
		   PyArrayObject *flags,
		   //PyArrayObject *rows,
		   PyArrayObject *sumwt,
		   int dopsf,
		   PyObject *Lcfs,
		   PyObject *LcfsConj,
		   PyArrayObject *Winfos,
		   PyArrayObject *increment,
		   PyArrayObject *freqs,
		   PyObject *Lmaps, PyObject *LJones, PyArrayObject *SmearMapping)
  {
    // Get size of convolution functions.
    PyArrayObject *cfs;
    PyArrayObject *NpPolMap;
    NpPolMap = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(Lmaps, 0), PyArray_INT32, 0, 4);
    int npolsMap=NpPolMap->dimensions[0];
    int* PolMap=I_ptr(NpPolMap);
    
    PyArrayObject *NpFacetInfos;
    NpFacetInfos = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(Lmaps, 1), PyArray_FLOAT64, 0, 4);

    PyArrayObject *NpRows;
    NpRows = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(Lmaps, 2), PyArray_INT32, 0, 4);
    int* ptrRows=I_ptr(NpRows);
    int row0=ptrRows[0];
    int row1=ptrRows[1];


    ////////////////////////////////////////////////////////////////////////////
    ////////////////////////////////////////////////////////////////////////////
    ////////////////////////////////////////////////////////////////////////////
    int LengthJonesList=PyList_Size(LJones);
    int DoApplyJones=0;
    PyArrayObject *npJonesMatrices, *npTimeMappingJonesMatrices, *npA0, *npA1, *npJonesIDIR, *npCoefsInterp,*npModeInterpolation;
    float complex* ptrJonesMatrices;
    int *ptrTimeMappingJonesMatrices,*ptrA0,*ptrA1,*ptrJonesIDIR;
    float *ptrCoefsInterp;
    int i_dir;
    int nd_Jones,na_Jones,nch_Jones,nt_Jones;

    printf("len %i",LengthJonesList);
    int JonesDims[4];
    int ModeInterpolation=1;
    int *ptrModeInterpolation;
    int ApplyAmp,ApplyPhase,DoScaleJones;
    float CalibError,CalibError2;
    if(LengthJonesList>0){
      DoApplyJones=1;

      npTimeMappingJonesMatrices  = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 0), PyArray_INT32, 0, 4);
      ptrTimeMappingJonesMatrices = p_int32(npTimeMappingJonesMatrices);

      npA0 = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 1), PyArray_INT32, 0, 4);
      ptrA0 = p_int32(npA0);
      int ifor;

      npA1= (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 2), PyArray_INT32, 0, 4);
      ptrA1=p_int32(npA1);
      
      // (nt,nd,na,1,2,2)
      npJonesMatrices = (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 3), PyArray_COMPLEX64, 0, 6);
      ptrJonesMatrices=p_complex64(npJonesMatrices);
      nt_Jones=(int)npJonesMatrices->dimensions[0];
      nd_Jones=(int)npJonesMatrices->dimensions[1];
      na_Jones=(int)npJonesMatrices->dimensions[2];
      nch_Jones=(int)npJonesMatrices->dimensions[3];
      JonesDims[0]=nt_Jones;
      JonesDims[1]=nd_Jones;
      JonesDims[2]=na_Jones;
      JonesDims[3]=nch_Jones;

      npJonesIDIR= (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 4), PyArray_INT32, 0, 4);
      ptrJonesIDIR=p_int32(npJonesIDIR);
      i_dir=ptrJonesIDIR[0];

      npCoefsInterp= (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 5), PyArray_FLOAT32, 0, 4);
      ptrCoefsInterp=p_float32(npCoefsInterp);

      npModeInterpolation= (PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LJones, 6), PyArray_INT32, 0, 4);
      ptrModeInterpolation=p_int32(npModeInterpolation);
      ModeInterpolation=ptrModeInterpolation[0];

      PyObject *_FApplyAmp  = PyList_GetItem(LJones, 7);
      ApplyAmp=(int) PyFloat_AsDouble(_FApplyAmp);
      PyObject *_FApplyPhase  = PyList_GetItem(LJones, 8);
      ApplyPhase=(int) PyFloat_AsDouble(_FApplyPhase);

      PyObject *_FDoScaleJones  = PyList_GetItem(LJones, 9);
      DoScaleJones=(int) PyFloat_AsDouble(_FDoScaleJones);
      PyObject *_FCalibError  = PyList_GetItem(LJones, 10);
      CalibError=(float) PyFloat_AsDouble(_FCalibError);
      CalibError2=CalibError*CalibError;

    };
    ////////////////////////////////////////////////////////////////////////////
    ////////////////////////////////////////////////////////////////////////////
    ////////////////////////////////////////////////////////////////////////////



    
    double VarTimeDeGrid=0;
    int Nop=0;

    double* ptrFacetInfos=p_float64(NpFacetInfos);
    double Cu=ptrFacetInfos[0];
    double Cv=ptrFacetInfos[1];
    double l0=ptrFacetInfos[2];
    double m0=ptrFacetInfos[3];
    double n0=sqrt(1-l0*l0-m0*m0)-1;


    //printf("npols=%i %i\n",npolsMap,PolMap[3]);

    // Get size of grid.
    double* ptrWinfo = p_float64(Winfos);
    double WaveRefWave = ptrWinfo[0];
    double wmax = ptrWinfo[1];
    double NwPlanes = ptrWinfo[2];
    int OverS=floor(ptrWinfo[3]);


    //printf("WaveRef=%f, wmax=%f \n",WaveRefWave,wmax);
    int nGridX    = grid->dimensions[3];
    int nGridY    = grid->dimensions[2];
    int nGridPol  = grid->dimensions[1];
    int nGridChan = grid->dimensions[0];
    
    // Get visibility data size.
    int nVisPol   = flags->dimensions[2];
    int nVisChan  = flags->dimensions[1];
    int nrows     = uvw->dimensions[0];
    //printf("(nrows, nVisChan, nVisPol)=(%i, %i, %i)\n",nrows,nVisChan,nVisPol);
    
    
    // Get oversampling and support size.
    int sampx = OverS;//int (cfs.sampling[0]);
    int sampy = OverS;//int (cfs.sampling[1]);
    
    double* __restrict__ sumWtPtr = p_float64(sumwt);//->data;
    double complex psfValues[4];
    psfValues[0] = psfValues[1] = psfValues[2] = psfValues[3] = 1;

    //uint inxRowWCorr(0);

    double offset_p[2],uvwScale_p[2];

    offset_p[0]=nGridX/2;//(nGridX-1)/2.;
    offset_p[1]=nGridY/2;
    float fnGridX=nGridX;
    float fnGridY=nGridY;
    double *incr=p_float64(increment);
    double *Pfreqs=p_float64(freqs);
    uvwScale_p[0]=fnGridX*incr[0];
    uvwScale_p[1]=fnGridX*incr[1];
    //printf("uvscale=(%f %f)",uvwScale_p[0],uvwScale_p[1]);
    double C=2.99792458e8;
    int inx;


    double posx,posy;

    float complex J0[4]={0},J1[4]={0},J0inv[4]={0},J1H[4]={0},J1Hinv[4]={0},JJ[4]={0};
    double WaveLengthMean=0.;
    int visChan;
    for (visChan=0; visChan<nVisChan; ++visChan){
      WaveLengthMean+=C/Pfreqs[visChan];
    }
    WaveLengthMean/=nVisChan;


    int *MappingBlock = p_int32(SmearMapping);
    int NTotBlocks=MappingBlock[0];
    int *NRowBlocks=MappingBlock+1;
    int *StartRow=MappingBlock+1+NTotBlocks;

    int iBlock;

    for(iBlock=0; iBlock<NTotBlocks; iBlock++){
    //for(iBlock=3507; iBlock<3508; iBlock++){
      int NRowThisBlock=NRowBlocks[iBlock]-2;
      int indexMap=StartRow[iBlock];
      int chStart=MappingBlock[indexMap];
      int chEnd=MappingBlock[indexMap+1];
      int *Row=MappingBlock+StartRow[iBlock]+2;

      float complex Vis[4]={0};
      float Umean=0;
      float Vmean=0;
      float Wmean=0;
      float FreqMean=0;
      int NVisThisblock=0;
      //printf("\n");
      //printf("Block[%i] Nrows=%i %i>%i\n",iBlock,NRowThisBlock,chStart,chEnd);

      for (inx=0; inx<NRowThisBlock; inx++) {
	int irow = Row[inx];
	if(irow>nrows){continue;}
	double*  __restrict__ uvwPtr   = p_float64(uvw) + irow*3;
	//printf("[%i] %i>%i bl=(%i-%i)\n",irow,chStart,chEnd,ptrA0[irow],ptrA1[irow]);
	//printf("  row=[%i] %i>%i \n",irow,chStart,chEnd);
	
	int ThisPol;
	for (visChan=chStart; visChan<chEnd; ++visChan) {
	  int doff = (irow * nVisChan + visChan) * nVisPol;
	  bool* __restrict__ flagPtr = p_bool(flags) + doff;
	  int OneFlagged=0;
	  int cond;
	  //char ch="a";
	  for(ThisPol =0; ThisPol<4;ThisPol++){
	    //cond=(flagPtr[ThisPol]==1);
	    //printf("  F[%i]: %i \n",ThisPol,cond);
	    if(flagPtr[ThisPol]==1){OneFlagged=1;}
	  }
	  if(OneFlagged){continue;}
	  
	  double U=uvwPtr[0];
	  double V=uvwPtr[1];
	  double W=uvwPtr[2];

	  U+=W*Cu;
	  V+=W*Cv;
	  //###################### Averaging #######################
	  Umean+=U;
	  Vmean+=V;
	  Wmean+=W;
	  FreqMean+=(float)Pfreqs[visChan];
	  NVisThisblock+=1;
	  //printf("      [%i,%i], fmean=%f %f\n",inx,visChan,(FreqMean/1e6),Pfreqs[visChan]);
	  
	}//endfor vischan
      }//endfor RowThisBlock
      if(NVisThisblock==0){continue;}
      Umean/=NVisThisblock;
      Vmean/=NVisThisblock;
      Wmean/=NVisThisblock;
      FreqMean/=NVisThisblock;

      //printf("  iblock: %i [%i], (uvw)=(%f, %f, %f) fmean=%f\n",iBlock,NVisThisblock,Umean,Vmean,Wmean,(FreqMean/1e6));
      /* int ThisPol; */
      /* for(ThisPol =0; ThisPol<4;ThisPol++){ */
      /* 	printf("   vis: %i (%f, %f)\n",ThisPol,creal(Vis[ThisPol]),cimag(Vis[ThisPol])); */
      /* } */
      

      // ################################################
      // ############## Start Gridding visibility #######
      int gridChan = 0;//chanMap_p[visChan];
      int CFChan = 0;//ChanCFMap[visChan];
      double recipWvl = FreqMean / C;
      double ThisWaveLength=C/FreqMean;

      // ############## W-projection ####################
      double wcoord=Wmean;
      /* int iwplane = floor((NwPlanes-1)*abs(wcoord)*(WaveRefWave/ThisWaveLength)/wmax); */
      /* int skipW=0; */
      /* if(iwplane>NwPlanes-1){skipW=1;continue;}; */
      
      /* if(wcoord>0){ */
      /* 	cfs=(PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(Lcfs, iwplane), PyArray_COMPLEX64, 0, 2); */
      /* } else{ */
      /* 	cfs=(PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LcfsConj, iwplane), PyArray_COMPLEX64, 0, 2); */
      /* } */
      /* int nConvX = cfs->dimensions[0]; */
      /* int nConvY = cfs->dimensions[1]; */
      /* int supx = (nConvX/OverS-1)/2; */
      /* int supy = (nConvY/OverS-1)/2; */
      /* int SupportCF=nConvX/OverS; */
      /* // ################################################ */


	int iwplane = floor((NwPlanes-1)*abs(wcoord)*(WaveRefWave/ThisWaveLength)/wmax+0.5);
	int skipW=0;
	if(iwplane>NwPlanes-1){skipW=1;continue;};

	//int iwplane = floor((NwPlanes-1)*abs(wcoord)/wmax);

	//printf("wcoord=%f, iw=%i \n",wcoord,iwplane);

	if(wcoord>0){
	  cfs=(PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(Lcfs, iwplane), PyArray_COMPLEX64, 0, 2);
	} else{
	  cfs=(PyArrayObject *) PyArray_ContiguousFromObject(PyList_GetItem(LcfsConj, iwplane), PyArray_COMPLEX64, 0, 2);
	}
	int nConvX = cfs->dimensions[0];
	int nConvY = cfs->dimensions[1];
	int supx = (nConvX/OverS-1)/2;
	int supy = (nConvY/OverS-1)/2;
	int SupportCF=nConvX/OverS;
	
	

      if (gridChan >= 0  &&  gridChan < nGridChan) {
      	double posx,posy;
      	//For Even/Odd take the -1 off
      	posx = uvwScale_p[0] * Umean * recipWvl + offset_p[0];//#-1;
      	posy = uvwScale_p[1] * Vmean * recipWvl + offset_p[1];//-1;
	
      	int locx = nint (posx);    // location in grid
      	int locy = nint (posy);
      	//printf("locx=%i, locy=%i\n",locx,locy);
      	double diffx = locx - posx;
      	double diffy = locy - posy;
      	//printf("diffx=%f, diffy=%f\n",diffx,diffy);
      	int offx = nint (diffx * sampx); // location in
      	int offy = nint (diffy * sampy); // oversampling
      	//printf("offx=%i, offy=%i\n",offx,offy);
      	offx += (nConvX-1)/2;
      	offy += (nConvY-1)/2;
      	// Scaling with frequency is not necessary (according to Cyril).
      	double freqFact = 1;
      	int fsampx = nint (sampx * freqFact);
      	int fsampy = nint (sampy * freqFact);
      	int fsupx  = nint (supx / freqFact);
      	int fsupy  = nint (supy / freqFact);

	
      	// Only use visibility point if the full support is within grid.
      	if (locx-supx >= 0  &&  locx+supx < nGridX  &&
      	    locy-supy >= 0  &&  locy+supy < nGridY) {
      	  ///            cout << "in grid"<<endl;
      	  // Get pointer to data and flags for this channel.
      	  //int doff = (irow * nVisChan + visChan) * nVisPol;
      	  //float complex* __restrict__ visPtr  = p_complex64(vis)  + doff;
      	  //bool* __restrict__ flagPtr = p_bool(flags) + doff;
      	  float complex ThisVis[4]={0};
	  
      	  int ipol;
	  
      	  // Handle a visibility if not flagged.
      	  /* for (ipol=0; ipol<nVisPol; ++ipol) { */
      	  /*   if (! flagPtr[ipol]) { */
      	  /* 	visPtr[ipol] = Complex(0,0); */
      	  /*   } */
      	  /* } */
	  
      	  //for (Int w=0; w<4; ++w) {
      	  //  Double weight_interp(Weights_Lin_Interp[w]);
      	  for (ipol=0; ipol<nVisPol; ++ipol) {
      	    //if (((int)flagPtr[ipol])==0) {
      	      // Map to grid polarization. Only use pol if needed.
      	      int gridPol = PolMap[ipol];
      	      if (gridPol >= 0  &&  gridPol < nGridPol) {
		
      		int goff = (gridChan*nGridPol + gridPol) * nGridX * nGridY;
      		int sy;
		
      		const float complex* __restrict__ gridPtr;
      		const float complex* __restrict__ cf0;
		
      		int io=(offy - fsupy*fsampy);
      		int jo=(offx - fsupx*fsampx);
      		int cfoff = io * OverS * SupportCF*SupportCF + jo * SupportCF*SupportCF;
      		cf0 =  p_complex64(cfs) + cfoff;
		
		
		
		
      		for (sy=-fsupy; sy<=fsupy; ++sy) {
      		  gridPtr =  p_complex64(grid) + goff + (locy+sy)*nGridX + locx-supx;
      		  int sx;
      		  for (sx=-fsupx; sx<=fsupx; ++sx) {
      		    ThisVis[ipol] += *gridPtr  * *cf0;
      		    cf0 ++;
      		    gridPtr++;
      		  }
      		}
      	      } // end if gridPol
	      
	      
	      
      	    //} // end if !flagPtr
      	  } // end for ipol
	  
	  // ###########################################################
	  // ################### Now do the correction #################

      for (inx=0; inx<NRowThisBlock; inx++) {
	int irow = Row[inx];
	if(irow>nrows){continue;}
	double*  __restrict__ uvwPtr   = p_float64(uvw) + irow*3;
	//printf("[%i] %i>%i bl=(%i-%i)\n",irow,chStart,chEnd,ptrA0[irow],ptrA1[irow]);
	//printf("  row=[%i] %i>%i \n",irow,chStart,chEnd);
	
	if(DoApplyJones){
	  int i_t=ptrTimeMappingJonesMatrices[irow];
	  int i_ant0=ptrA0[irow];
	  int i_ant1=ptrA1[irow];
	  GiveJones(ptrJonesMatrices, JonesDims, ptrCoefsInterp, i_t, i_ant0, i_dir, ModeInterpolation, J0);
	  GiveJones(ptrJonesMatrices, JonesDims, ptrCoefsInterp, i_t, i_ant1, i_dir, ModeInterpolation, J1);
	  NormJones(J0, ApplyAmp, ApplyPhase, DoScaleJones, uvwPtr, WaveLengthMean, CalibError);
	  NormJones(J1, ApplyAmp, ApplyPhase, DoScaleJones, uvwPtr, WaveLengthMean, CalibError);
	  MatH(J1,J1H);
	} //endif DoApplyJones

	int ThisPol;
	for (visChan=chStart; visChan<chEnd; ++visChan) {
	  int doff = (irow * nVisChan + visChan) * nVisPol;
	  bool* __restrict__ flagPtr = p_bool(flags) + doff;
	  int OneFlagged=0;
	  int cond;
	  //char ch="a";
	  for(ThisPol =0; ThisPol<4;ThisPol++){
	    //cond=(flagPtr[ThisPol]==1);
	    //printf("  F[%i]: %i \n",ThisPol,cond);
	    if(flagPtr[ThisPol]==1){OneFlagged=1;}
	  }
	  if(OneFlagged){continue;}
	  
	  //###################### Facetting #######################
	  // Change coordinate and shift visibility to facet center
	  double ThisWaveLength=C/Pfreqs[visChan];
	  double complex UVNorm=2.*I*PI/ThisWaveLength;
	  double U=uvwPtr[0];
	  double V=uvwPtr[1];
	  double W=uvwPtr[2];
	  float complex corr=cexp(UVNorm*(U*l0+V*m0+W*n0));
	  /* double ThisWaveLength=C/FreqMean; */
	  /* double complex UVNorm=2.*I*PI/ThisWaveLength; */
	  /* double U=Umean; */
	  /* double V=Vmean; */
	  /* double W=Wmean; */
	  /* float complex corr=cexp(UVNorm*(U*l0+V*m0+W*n0)); */
	  //#######################################################

	  float complex* __restrict__ visPtr  = p_complex64(vis)  + doff;
	  float complex visBuff[4]={0};
	  if(DoApplyJones){
	    MatDot(J0,ThisVis,visBuff);
	    MatDot(visBuff,J1H,visBuff);
	    for(ThisPol =0; ThisPol<4;ThisPol++){
	      visPtr[ThisPol]-=visBuff[ThisPol]*(corr);
	    }
	  }else{
	    for(ThisPol =0; ThisPol<4;ThisPol++){
	      visPtr[ThisPol]-=ThisVis[ThisPol]*(corr);
	    }
	  };


	  
	}//endfor vischan
      }//endfor RowThisBlock


	  
      	} // end if ongrid
      } // end if gridChan
      
    } //end for Block
    
  } // end 
