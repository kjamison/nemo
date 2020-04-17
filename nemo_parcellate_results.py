import numpy as np
import nibabel as nib
from scipy import sparse
import sys
import time
import argparse 
import multiprocessing
from scipy.io import savemat


parser=argparse.ArgumentParser(description='Parcellate ChaCo maps into ROIs')

parser.add_argument('--input','-i',action='store', dest='chacofile')
#parser.add_argument('--inputlist','-il',action='store', dest='chacolist')
parser.add_argument('--output','-o',action='store', dest='outputbase')
parser.add_argument('--parcelvol','-p',action='store', dest='parcelfile')
parser.add_argument('--refvol','-r',action='store', dest='refimgfile')
parser.add_argument('--endpointmask','-m',action='store', dest='endpointmaskfile')
parser.add_argument('--asum','-a',action='store', dest='asumfile')
parser.add_argument('--style2','-s2',action='store_true',dest='style2')

args=parser.parse_args()

chaco_allsubj=sparse.load_npz(args.chacofile)

refimg=nib.load(args.refimgfile)
parcelimg=nib.load(args.parcelfile)
endpointmask_allsubj=sparse.load_npz(args.endpointmaskfile)
outfile=args.outputbase
asumfile=args.asumfile
do_style2=args.style2

if do_style2 and asumfile is None:
    print('Must provide --asum input for style2')
    exit(1)

numsubj=chaco_allsubj.shape[0]
numvoxels=chaco_allsubj.shape[1]

Pdata=np.round(parcelimg.get_fdata()).flatten()
pmaskidx=np.where(Pdata!=0)[0]
uroi, uidx=np.unique(Pdata[Pdata!=0],return_inverse=True)

Psparse=sparse.csr_matrix((np.ones(pmaskidx.size),(pmaskidx,uidx)),shape=(numvoxels,len(uroi)),dtype=np.float32)

if do_style2:
    Asum=sparse.load_npz(asumfile)
    endpointAsum=endpointmask_allsubj.multiply(Asum)
    roi_chaco_allsubj=(chaco_allsubj.multiply(endpointAsum) @ Psparse) / (endpointAsum @ Psparse)
    savemat(outfile,{'roi_chaco_allref': roi_chaco_allsubj})
else:
    roi_chaco_allsubj=np.array((chaco_allsubj @ Psparse) /  (endpointmask_allsubj @ Psparse),dtype=np.float64)
    savemat(outfile,{'roi_chaco_allref': roi_chaco_allsubj})



#chaco_allsubj = 420x7M (only at endpoints)
#endpointmask = 420x7M (only at endpoints)
#Asum = 420x7M (denser)
#chaco_allsubj * (Asum * endpointmask)
#numerator = (chaco_allsubj * (Asum * endpointmask)) @ Psparse
#denom = (Asum * endpointmask) @ Psparse
