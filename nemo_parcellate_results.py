import numpy as np
import nibabel as nib
import nibabel.processing
from scipy import sparse
import sys
import time
import argparse 
import multiprocessing
from scipy.io import savemat
import pickle

##########

def createSparseDownsampleParcellation(newvoxmm, origvoxmm, volshape, refimg):
    chunksize=newvoxmm*newvoxmm*newvoxmm
    chunkvec_x=np.int32(np.floor(np.arange(volshape[0])/newvoxmm))
    chunkvec_y=np.int32(np.floor(np.arange(volshape[1])/newvoxmm))
    chunkvec_z=np.int32(np.floor(np.arange(volshape[2])/newvoxmm))

    chunkvec_size=(chunkvec_x[-1]+1, chunkvec_y[-1]+1, chunkvec_z[-1]+1)
                                  
    chunky,chunkx,chunkz=np.meshgrid(chunkvec_y,chunkvec_x,chunkvec_z)

    #a volsize 3D array where each entry is a 0-numchunks index
    chunkidx=chunkz + chunky*chunkvec_size[0] + chunkx*chunkvec_size[0]*chunkvec_size[1]
    #a voxidx x 1 array where chunkidx_flat(voxidx)=chunk index
    chunkidx_flat=chunkidx.flatten()
    numchunks=np.max(chunkidx)+1

    newvolshape=np.ceil(np.array(volshape)/newvoxmm).astype(np.int32)

    numvoxels=np.prod(volshape)
    newnumvoxels=np.prod(newvolshape)

    unique_chunks, uidx =np.unique(chunkidx_flat, return_inverse=True)

    Psparse=sparse.csr_matrix((np.ones(numvoxels),(range(numvoxels),uidx)),shape=(numvoxels,numchunks),dtype=np.float32)
    
    newaff=refimg.affine.copy()
    newaff[:3,:3]*=newvoxmm/origvoxmm
    
    #because voxel center is 0.5 in orig and 0.5*res in the new one, we need to add a small shift to the new reference volume so it properly overlays
    voxoffset=(newvoxmm-origvoxmm)/2.0
    newaff[:3,-1]+np.sign(refimg.affine[:3,:3]) @ [voxoffset,voxoffset,voxoffset]
    newrefimg=nib.processing.resample_from_to(refimg,(newvolshape,newaff),order=0)

    return Psparse, newvolshape, newrefimg

def flatParcellationToTransform(Pflat, isubj=None, out_type="csr"):
    if sparse.issparse(Pflat):
        Pdata=Pflat[isubj,:].toarray().flatten()
    elif isubj is None:
        Pdata=Pflat.flatten()
    elif len(Pdata.shape)==2:
        Pdata=Pflat[isubj,:].flatten()
            
    numvoxels=np.prod(Pdata.shape)
    pmaskidx=np.where(Pdata!=0)[0]
    uroi, uidx=np.unique(Pdata[Pdata!=0],return_inverse=True)
    numroi=len(uroi)
    
    #this would create an entry at the actual ROI values, rather than just going through the sequential PRESENT value
    #eg: for cc400 it would be a 7M x 400 array instead of 7M x 392
    #   but for an arbitrary/custom input, where they left freesurfer values, this could make it in the thousands!
    #uidx=(uroi[uidx]-1).astype(np.int64)
    #numroi=max(uroi).astype(np.int64)
    
    if out_type == "csr":
        return sparse.csr_matrix((np.ones(pmaskidx.size),(pmaskidx,uidx)),shape=(numvoxels,numroi),dtype=np.float32)
    elif out_type == "csc":
        return sparse.csc_matrix((np.ones(pmaskidx.size),(pmaskidx,uidx)),shape=(numvoxels,numroi),dtype=np.float32)
        
##########

parser=argparse.ArgumentParser(description='Parcellate ChaCo maps into ROIs')

parser.add_argument('--input','-i',action='store', dest='chacofile')
#parser.add_argument('--inputlist','-il',action='store', dest='chacolist')
parser.add_argument('--output','-o',action='store', dest='outputbase')
parser.add_argument('--outputmean','-om',action='store', dest='outputbasemean')
parser.add_argument('--outputstdev','-os',action='store', dest='outputbasestd')
parser.add_argument('--parcelvol','-p',action='store', dest='parcelfile')
parser.add_argument('--resolution','-res',action='store', dest='resolution')
parser.add_argument('--refvol','-r',action='store', dest='refimgfile')
#parser.add_argument('--endpointmask','-m',action='store', dest='endpointmaskfile')
parser.add_argument('--asum','-a',action='store', dest='asumfile')
#parser.add_argument('--style2','-s2',action='store_true',dest='style2')

args=parser.parse_args()

if args.chacofile.endswith(".npz"):
    chaco_allsubj=sparse.load_npz(args.chacofile)
elif args.chacofile.endswith(".pkl"):
    chaco_allsubj=pickle.load(open(args.chacofile,"rb"))

refimg=nib.load(args.refimgfile)
#endpointmask_allsubj=sparse.load_npz(args.endpointmaskfile)
outfile=args.outputbase
outmeanfile=args.outputbasemean
outstdfile=args.outputbasestd
asumfile=args.asumfile
#do_style2=args.style2

#if do_style2 and asumfile is None:
#    print('Must provide --asum input for style2')
#    exit(1)

numsubj=chaco_allsubj.shape[0]
numvoxels=chaco_allsubj.shape[1]

newvolshape=None
newrefimg=None

if args.parcelfile:    
    parcelimg=nib.load(args.parcelfile)
    Pdata=np.round(parcelimg.get_fdata()).flatten()
    Psparse=flatParcellationToTransform(Pdata, None, out_type="csr")
    
if args.resolution:
    try:
        newvoxmm=round(abs(float(args.resolution)))
    except ValueError:
        raise(Exception("Resampling resolution must be a numerical value"))

    origvoxmm=1
    Psparse, newvolshape, newrefimg = createSparseDownsampleParcellation(newvoxmm, origvoxmm, refimg.shape, refimg)
    
    
#if do_style2:

endpointAsum=sparse.load_npz(asumfile)
#endpointAsum=endpointmask_allsubj.multiply(Asum)
roi_chaco_allsubj_denom=endpointAsum @ Psparse
roi_chaco_allsubj_denom.data=1/roi_chaco_allsubj_denom.data.astype(np.float32)
#roi_chaco_allsubj=(chaco_allsubj.multiply(endpointAsum) @ Psparse) / (endpointAsum @ Psparse)
roi_chaco_allsubj=(chaco_allsubj.multiply(endpointAsum) @ Psparse).multiply(roi_chaco_allsubj_denom)
chacomean=np.array(np.mean(roi_chaco_allsubj,axis=0))
        
if outfile:
    #savemat(outfile,{'roi_chaco_allref': roi_chaco_allsubj})
    sparse.save_npz(outfile,roi_chaco_allsubj,compressed=False)
if outmeanfile:
    if newvolshape is not None:
        imgchaco=nib.Nifti1Image(np.reshape(chacomean,newvolshape),affine=newrefimg.affine, header=newrefimg.header)
        nib.save(imgchaco,outmeanfile)
    else:
        np.savetxt(outmeanfile,np.mean(roi_chaco_allsubj,axis=0),fmt="%.10f",delimiter=",")
if outstdfile:
    if newvolshape is not None:
        chacostd=np.sqrt(np.array(np.mean(roi_chaco_allsubj.multiply(roi_chaco_allsubj),axis=0) - chacomean**2))
        imgchaco_std=nib.Nifti1Image(np.reshape(chacostd,newvolshape),affine=newrefimg.affine, header=newrefimg.header)
        nib.save(imgchaco_std,outstdfile)
    else:
        np.savetxt(outstdfile,np.std(roi_chaco_allsubj,axis=0),fmt="%.10f",delimiter=",")

#else:
#    roi_chaco_allsubj=np.array((chaco_allsubj @ Psparse) /  (endpointmask_allsubj @ Psparse),dtype=np.float64)
#    savemat(outfile,{'roi_chaco_allref': roi_chaco_allsubj})
#    np.savetxt(outmeanfile,np.mean(roi_chaco_allsubj,axis=0),fmt="%.10f",delimiter=",")



#chaco_allsubj = 420x7M (only at endpoints)
#endpointmask = 420x7M (only at endpoints)
#Asum = 420x7M (denser)
#chaco_allsubj * (Asum * endpointmask)
#numerator = (chaco_allsubj * (Asum * endpointmask)) @ Psparse
#denom = (Asum * endpointmask) @ Psparse
