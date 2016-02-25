# DDFacet

## Dependencies

From an Ubuntu 14.04 base:

```
sudo pip install SharedArray
sudo pip install Polygon2
sudo pip install pyFFTW
sudo apt-get install python-casacore libfftw3-dev python-pyephem python-numexpr cython
```

Then need to clone or checkout the following three:

```
git clone git@github.com:cyriltasse/SkyModel.git
git clone git@github.com:cyriltasse/killMS2.git
git clone git@github.com:cyriltasse/DDFacet.git

```

## Build

Build a few libraries:

```
(cd DDFacet/Gridder ; make)
(cd ./killMS2/Predict ; make)
(cd ./killMS2/Predict ; make)
```

## Paths etc.

Add this to your ``.bashrc``

```
export KILLMS_DIR=$HOME/projects   ### or whereever you've git cloned the repos
export DDFACET_DIR=$KILLMS_DIR
export PYTHONPATH=$PYTHONPATH:$KILLMS_DIR
export LD_LIBRARY_PATH=$KILLMS_DIR/DDFacet/Gridder:$LD_LIBRARY_PATH
export PATH=$KILLMS_DIR/killMS2:$KILLMS_DIR/SkyModel:$KILLMS_DIR/DDFacet:$PATH
```

