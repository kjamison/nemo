import numpy as np
#from scipy import sparse
from scipy.io import loadmat
import sys
import time
import nibabel as nib
import argparse

def argument_parse():
    parser=argparse.ArgumentParser()

    parser.add_argument('--subjects','-s',action='store', dest='subjlist', required=True)
    parser.add_argument('--fileroot','-f',action='store', dest='fileroot', required=True)
    parser.add_argument('--output','-o',action='store', dest='outfile', required=True)
    parser.add_argument('--ref','-r',action='store', dest='refvolfile')
    parser.add_argument('--algo','-a',action='store', dest='algo',default='ifod2act5Mfsl')
    parser.add_argument('--numtracks','-n',action='store', dest='numtracks',default='5M')
    parser.add_argument('--chunkvox','-c',action='store', type=int, dest='chunkvoxsize',default=10)

    return parser.parse_args()

if __name__ == "__main__":
    args=argument_parse()

    subjectlistfile=args.subjlist
    fileroot=args.fileroot
    outfile=args.outfile
    algo=args.algo
    numtrackstr=args.numtracks
    refvolfile=args.refvolfile
    chunkvoxsize=args.chunkvoxsize
	
    subjfid=open(subjectlistfile,'r')
    subjects=[x.strip() for x in subjfid.readlines()]
    subjfid.close()

    #algo='ifod2act5Mfsl'
    #numtrackstr='5M'

    numsubj=len(subjects)

    #############
    if refvolfile:
        refimg=nib.load(refvolfile)
        volshape=refimg.shape
    else:
        volshape=np.array([182,218,182])
    
    chunksize=chunkvoxsize*chunkvoxsize*chunkvoxsize
    chunkvec_x=np.int32(np.floor(np.arange(volshape[0])/chunkvoxsize))
    chunkvec_y=np.int32(np.floor(np.arange(volshape[1])/chunkvoxsize))
    chunkvec_z=np.int32(np.floor(np.arange(volshape[2])/chunkvoxsize))

    chunkvec_size=(chunkvec_x[-1]+1, chunkvec_y[-1]+1, chunkvec_z[-1]+1)
                                      
    chunky,chunkx,chunkz=np.meshgrid(chunkvec_y,chunkvec_x,chunkvec_z)

    #a volsize 3D array where each entry is a 0-numchunks index
    chunkidx=chunkz + chunky*chunkvec_size[0] + chunkx*chunkvec_size[0]*chunkvec_size[1]
    #a voxidx x 1 array where chunkidx_flat(voxidx)=chunk index
    chunkidx_flat=chunkidx.flatten()
    numchunks=np.max(chunkidx)+1

    #############
    starttime=time.time()
    Asum=[]
    subject_sparsefiles=[]
    numtracks=None
    for isubj,subj in enumerate(subjects):
        sparsefile='%s/mnitracks_%s_%s/%s_%s_%s_MNI_sparsemat.mat' % (fileroot,subj,algo,subj,algo,numtrackstr)
        subject_sparsefiles.append(sparsefile)
        Atmp=loadmat(sparsefile,variable_names=['Asum'])['Asum']
        if isubj == 0:
            Asum=Atmp
            print(Asum.shape)
        else:
            Asum+=Atmp

        if numtracks is None:
            numtracks=loadmat(sparsefile,variable_names=['track_weights'])['track_weights'].size

        if isubj > 0 and isubj % 5 == 0:
            print('Loading %d/%d took %.3f seconds' % (isubj,len(subjects),time.time()-starttime))

    #Asum=Asum.todense().squeeze()
    Asum=np.array(Asum.todense()).squeeze()
    Amask=Asum>0
    unique_chunks=np.unique(chunkidx_flat[Amask])
    np.savez(outfile,Asum=Asum, Amask=Amask, subjects=subjects, subject_sparsefiles=subject_sparsefiles, \
    	volshape=volshape, chunkvoxsize=chunkvoxsize, chunksize=chunksize, chunkidx=chunkidx, \
    	chunkidx_flat=chunkidx_flat, numchunks=numchunks, unique_chunks=unique_chunks, num_unique_chunks=len(unique_chunks), \
    	numtracks=numtracks)

