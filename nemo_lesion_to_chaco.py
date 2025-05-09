import multiprocessing
import os
from pathlib import Path 
import numpy as np
import nibabel as nib
import nibabel.processing
import time
import sys
from scipy import sparse
from matplotlib import pyplot as plt
from nilearn import plotting, image
from scipy import ndimage
import argparse 
import tempfile
import subprocess
import boto3
import pickle
import shutil
from itertools import repeat

def argument_parse(arglist):
    parser=argparse.ArgumentParser(description='Read lesion mask and create voxel-wise ChaCo maps for all reference subjects')
    parser.add_argument('--lesion','-l',action='store', dest='lesion')
    parser.add_argument('--outputbase','-o',action='store', dest='outputbase')
    parser.add_argument('--chunklist','-c',action='store', dest='chunklist')
    parser.add_argument('--chunkdir','-cd',action='store', dest='chunkdir')
    parser.add_argument('--refvol','-r',action='store', dest='refvol')
    parser.add_argument('--endpoints','-e',action='store', dest='endpoints')
    parser.add_argument('--endpointsmask','-em',action='store', dest='endpointsmask')
    parser.add_argument('--asum','-a',action='store', dest='asum')
    parser.add_argument('--asum_weighted','-aw',action='store', dest='asum_weighted')
    parser.add_argument('--asum_cumulative','-ac',action='store', dest='asum_cumulative')
    parser.add_argument('--asum_weighted_cumulative','-acw',action='store', dest='asum_weighted_cumulative')
    parser.add_argument('--trackweights','-t',action='store', dest='trackweights')
    parser.add_argument('--tracklengths','-tl',action='store',dest='tracklengths')
    parser.add_argument('--weighted','-w',action='store_true', dest='weighted')
    parser.add_argument('--smoothed','-s',action='store_true', dest='smoothed')
    parser.add_argument('--smoothfwhm','-sw',default=6, action='store', dest='smoothfwhm', help = 'default: %(default)d')
    parser.add_argument('--smoothmode','-sm',default='ratio', action='store', dest='smoothmode', choices=['ratio','counts'], help = 'default: %(default)s')
    parser.add_argument('--s3nemoroot','-s3',action='store', dest='s3nemoroot')
    parser.add_argument('--parcelvol','-p',action='append', dest='parcelvol')
    parser.add_argument('--resolution','-res',action='append', dest='resolution')
    parser.add_argument('--cumulative',action='store_true', dest='cumulative')
    parser.add_argument('--pairwise',action='store_true', dest='pairwise')
    parser.add_argument('--continuous_value',action='store_true', dest='continuous_value')
    parser.add_argument('--tracking_algorithm',action='store',dest='tracking_algorithm')
    parser.add_argument('--debug',action='store_true', dest='debug')
    parser.add_argument('--subjcount',action='store', dest='subjcount', type=int, help='number of reference subjects to compute (for debugging only!)')
    parser.add_argument('--onlynonzerodenom',action='store_true',dest='only_nonzero_denom', help='only include subjects with non-zero denominator for a given voxel')
    
    return parser.parse_args(arglist)

def durationToString(numseconds):
    if numseconds < 60:
        return "%.3f seconds" % (numseconds)
    newms = numseconds % 1
    newseconds = int(numseconds) % 60
    newminutes = int(numseconds / 60) % 60
    newhours = int(numseconds / (60*60)) % 24
    newdays = int(numseconds / (60*60*24))
    newstring=""
    if newdays > 0:
        newstring+="%gd" % (newdays)
    if newhours > 0:
        newstring+="%gh" % (newhours)
    if newminutes > 0:
        newstring+="%gm" % (newminutes)
    if newms > 0:
        newstring+="%.3fs" % (newseconds+newms)
    elif newseconds > 0:
        newstring+="%gs" % (newseconds)
    return newstring

def createSparseDownsampleParcellation(newvoxmm, origvoxmm, volshape, refimg):
    #chunksize=newvoxmm*newvoxmm*newvoxmm
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
    newaff[:3,-1]+=np.sign(refimg.affine[:3,:3]) @ [voxoffset,voxoffset,voxoffset]
    newrefimg=nib.processing.resample_from_to(refimg,(newvolshape,newaff),order=0)
    
    return Psparse, newvolshape, newrefimg

def flatParcellationToTransform(Pflat, isubj=None, out_type="csr", max_sequential_roi_value=None):
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
    
    if max_sequential_roi_value is not None:
        #this would create an entry at the actual ROI values, rather than just going through the sequential PRESENT value
        #eg: for cc400 it would be a 7M x 400 array instead of 7M x 392
        #   but for an arbitrary/custom input, where they left freesurfer values, this could make it in the thousands!
        uidx=(uroi[uidx]-1).astype(np.int64)
        numroi=max_sequential_roi_value.astype(np.int64)
    
    if out_type == "csr":
        return sparse.csr_matrix((np.ones(pmaskidx.size),(pmaskidx,uidx)),shape=(numvoxels,numroi),dtype=np.float32)
    elif out_type == "csc":
        return sparse.csc_matrix((np.ones(pmaskidx.size),(pmaskidx,uidx)),shape=(numvoxels,numroi),dtype=np.float32)

def checkVolumeShape(Pimg, refimg, filename_display, expected_shape, expected_shape_spm):
    imgshape=Pimg.shape
    if len(imgshape)>=4 and  all([x==1 for x in imgshape[3:]]):
        #some nii files include a 4th dimension even for single volumes (eg: outputs from nifti_4dfp)
        #if all dimensions>3 are just 1, just flatten and reshape to correct 3D
        Pimg=nib.Nifti1Image(np.reshape(Pimg.get_fdata().flatten()[:np.prod(imgshape)],imgshape[:3]),affine=Pimg.affine,header=Pimg.header)
        imgshape=Pimg.shape
    if imgshape == expected_shape:
        #seems correct
        #pass
        #resample no matter in case there's some LPI vs RPI issue
        Pimg=nibabel.processing.resample_from_to(Pimg,refimg,order=0)
    elif imgshape == expected_shape_spm:
        #print('%s was 181x217x181, not the expected 182x218x181. Assuming SPM-based reg and padding end of each dim.' % (filename_display))
        #Pdata=np.pad(Pdata,(0,1),mode='constant')
        print('%s was 181x217x181, not the expected 182x218x182. Resampling to expected.' % (filename_display))
        Pimg=nibabel.processing.resample_from_to(Pimg,refimg,order=0)
    else:
        shapestr=",".join([str(x) for x in Pimg.shape])
        raise(Exception('Unexpected volume size: (%s) for %s. Each input must be a SINGLE volume registered to 182x218x182 MNIv6 template (FSL template)' % (shapestr,filename_display)))
    return Pimg

def smooth_sparse_vol(sparsevals, fwhm, volshape, voxmm):
    outsmooth=sparse.csr_matrix(ndimage.gaussian_filter(np.reshape(np.array(sparsevals.todense()),volshape),sigma=fwhm/2.35482/voxmm).flatten())
    outsmooth.eliminate_zeros()
    return outsmooth

############################################################
############################################################
############################################################

# multiprocessing.map functions

# * only take a single iterable input
# * each requires certain externally defined READ-ONLY variables
#   (trying to avoid passing these as additional arguments because they are large
#   and I'm worried they will take up additional memory in each subprocess. 
#   In Linux+Mac, this should work just fine. In Windows, this might fail)
# * Note these external variables can't be defined inside a function, so "main" has
#   to be inside an "if" but not a "def main():"

#original:
#Mapping to endpoints and ChaCo took 4.252 seconds on 15 threads
#Mapping to conn  took 2.511 seconds on 15 threads

#now with T.eliminate_zeros() in map_to_endpoints() also:
#Mapping to endpoints and ChaCo took 2.222 seconds on 15 threads
#Mapping to conn  took 2.420 seconds on 15 threads
###########################################################

# make a per process s3_client
nemo_s3_client = None

def s3initialize():
    global nemo_s3_client
    nemo_s3_client = boto3.client('s3')

def s3download(job):
    bucket, key, filename = job
    nemo_s3_client.download_file(bucket,key,filename)

def save_lesion_chunk(whichchunk):
    #externals: chunkfile_fmt, tmpchunkfile_fmt, Lmask, chunkidx_flat, numsubj, do_cumulative_hits, chunksize
    subjchunksA=sparse.load_npz(chunkfile_fmt % (whichchunk))
    Lchunk=Lmask[chunkidx_flat==whichchunk]
    
    #some chunks around the edge of the volume don't have the full 1000 voxels!
    #make sure we get the size of this specific chunk so matrix multiplications agree
    chunksize_thischunk=len(Lchunk)
    
    chunktrackmask=[]
    
    for isubj in range(numsubj):
        #binarize the T matrix (each streamline is hit or not) here
        #If we remove this, we have to figure out the denominator for ChaCo (currently Asum = total number of streamlines at each endpoint)
        if do_cumulative_hits:
            chunktrackmask.append(sparse.csr_matrix(Lchunk @ subjchunksA[(isubj*chunksize_thischunk):((isubj+1)*chunksize_thischunk),:]))
        else:
            chunktrackmask.append(sparse.csr_matrix(Lchunk @ subjchunksA[(isubj*chunksize_thischunk):((isubj+1)*chunksize_thischunk),:])>0)
        chunktrackmask[-1].eliminate_zeros()
    
    tmpfilename=tmpchunkfile_fmt % (whichchunk)
    sparse.save_npz(tmpfilename,sparse.vstack(chunktrackmask),compressed=False)
    return whichchunk

def map_to_endpoints(isubj):
    #externals: endpointmat, numsubj, tidx, numtracks, numvoxels, do_weighted, T_allsubj, trackweights, Asum, tmpdir
    endpt=endpointmat[(isubj,isubj+numsubj),:].flatten()
    #note: create this as a float32 so later mult properly SUMS columns instead of just logical
    B=sparse.csr_matrix((np.ones(tidx.shape,dtype=np.float32),(tidx,endpt)),shape=(numtracks,numvoxels))
    
    if do_weighted:
        chacovol=((T_allsubj[isubj,:]).multiply(trackweights[isubj,:]) @ B).multiply(Asum[isubj,:])
    else:   
        chacovol=(T_allsubj[isubj,:] @ B).multiply(Asum[isubj,:])
    #any endpoints for "voxel 0" are from spurious endpoints for "lost" streamlines
    chacovol[0]=0
    chacovol.eliminate_zeros()
    chacofile_subj=tmpdir+'/chacovol_subj%05d.npz' % (isubj)
    sparse.save_npz(chacofile_subj,chacovol,compressed=False)
    
    #if Psparse_list:
    #    for Psparse in Psparse_list:
    #        #chacovol_parc=((T_allsubj[isubj,:]>0) @ (B @ Psparse)).multiply(Asum[isubj,:] @ Psparse))

def map_to_endpoints_numerator(isubj):
    #externals: endpointmat, numsubj, tidx, numtracks, numvoxels, T_allsubj, trackweights, tmpdir, Psparse_list
    
    endpt=endpointmat[(isubj,isubj+numsubj),:]
    endpt_iszero=np.any(endpt==0,axis=0)
    #note: create this as a float32 so later mult properly SUMS columns instead of just logical
    B=sparse.csr_matrix((np.ones(tidx.shape,dtype=np.float32),(tidx,endpt.flatten())),shape=(numtracks,numvoxels))
    
    T=T_allsubj[isubj,:].astype(np.float32)
    if trackweights is not None:
        T.data*=trackweights[isubj,T.indices]
        
    T.data[endpt_iszero[T.indices]]=0
    
    chacovol=T @ B
    
    #any endpoints for "voxel 0" are from spurious endpoints for "lost" streamlines
    #!!!!!! chacovol[0]=0
    chacovol.eliminate_zeros()
    chacofile_subj=tmpdir+'/chacovol_subj%05d.npz' % (isubj)
    sparse.save_npz(chacofile_subj,chacovol,compressed=False)
    
    #Need to get an Asum and Asum_weighted that accounts for tracklengths!
    #if do_compute_denom:
    #    if do_cumulative_hits:
    #        denom_val=Asum[isubj,:].copy()
    #    else:
    #        denom_val=Asum[isubj,:].copy()
    #    something;
    
    if Psparse_list:
        for iparc, Pdict in enumerate(Psparse_list):
            if isinstance(Pdict['transform'],list):
                #stored as csc to need to transpose
                chacovol_parc=chacovol @ Pdict['transform'][isubj].tocsr()
            else:
                chacovol_parc=chacovol @ Pdict['transform']
            
            chacovol_parc.eliminate_zeros()
            
            chacofile_subj=tmpdir+'/chacovol_parc%05d_subj%05d.npz' % (iparc,isubj)
            sparse.save_npz(chacofile_subj,chacovol_parc,compressed=False)

###########################################################
def map_to_endpoints_conn(isubj):
    #externals: endpointmat, numsubj, T_allsubj, trackweights, numvoxels, tmpdir, do_save_fullconn, do_compute_denom, do_cumulative_hits, tracklengths, Psparse_list 
    endpt=endpointmat[(isubj,isubj+numsubj),:]
    endpt1=endpt.min(axis=0)
    endpt2=endpt.max(axis=0)
    #any endpoints in "voxel 0" are from spurious endpoints for "lost" streamlines
    endpt_iszero=(endpt1==0) | (endpt2==0)
    #chacoconn=sparse.csr_matrix(((T_allsubj[isubj,:]>0).toarray().flatten(),(endpt1,endpt2)),shape=(numvoxels,numvoxels),dtype=np.float32)
    
    #note: need to cast to non-bool here otherwise the summing in sparse matrix build doesn't work!
    T=T_allsubj[isubj,:].astype(np.float32)
    if trackweights is not None:
        T.data*=trackweights[isubj,T.indices]
    T.data[endpt_iszero[T.indices]]=0
    #T.eliminate_zeros()
    chacoconn=sparse.csr_matrix((T.data,(endpt1[T.indices],endpt2[T.indices])),shape=(numvoxels,numvoxels),dtype=np.float32)
    
    #sparse.save_npz(tmpdir+'/chacoconnAconnsum_subj%05d.npz' % (isubj),Aconnsum,compressed=False)
    
    
    chacovol=sparse.csr_matrix(chacoconn.sum(axis=0)+sparse.triu(chacoconn,k=1).sum(axis=1).T)
    #!!!!! chacovol[0]=0
    chacovol.eliminate_zeros()
    chacofile_subj=tmpdir+'/chacovol_subj%05d.npz' % (isubj)
    sparse.save_npz(chacofile_subj,chacovol,compressed=False)
    
    #might not want the full voxel x voxel connectivity matrix (probably don't!)
    if do_save_fullconn:
        chacofile_subj=tmpdir+'/chacoconn_subj%05d.npz' % (isubj)
        #sparse.save_npz(chacofile_subj,chacoconn.multiply(Aconnsum),compressed=False)
        sparse.save_npz(chacofile_subj,chacoconn,compressed=False)
    
    #chacoconn file is 40MB per subject (*420=16.8GB) for 375chunk lesion, 28MB per subject (*420=11.8GB) for the smallest lesion
    #takes about 2.7x as long as simple chacovol
    
    #we might want to use a PREcomputed Aconnsum denominator. Bigger file (12GB) but faster calculation
    #however computing it here is more flexible IF we want to compute 
    if do_compute_denom:
        if trackweights is None:
            denom_val=np.ones(endpt1.size,dtype=np.float32)
        else:
            denom_val=trackweights[isubj,:].copy()
        
        if do_cumulative_hits:
            #denominator should assume hits along ENTIRE length in this case
            denom_val*=tracklengths[isubj,:]
        
        denom_val[endpt_iszero]=0
        
        #only need to store denominator when numerator (T) is non-zero
        #actually no! since we use this for parcellation we will lose all the other voxels in the parcel and the parcellated ratios will all be ~1!
        #Aconnsum=sparse.csr_matrix((denom_val[T.indices],(endpt1[T.indices],endpt2[T.indices])),shape=(numvoxels,numvoxels),dtype=np.float32)
        Aconnsum=sparse.csr_matrix((denom_val,(endpt1,endpt2)),shape=(numvoxels,numvoxels),dtype=np.float32)
        Aconnsum.eliminate_zeros()
        if do_save_fullconn:
            chacofile_subj=tmpdir+'/chacoconn_denom_subj%05d.npz' % (isubj)
            sparse.save_npz(chacofile_subj,Aconnsum,compressed=False)
        
        #compute the full voxelwise denom here since it doesn't take that long relative to other 
        #steps and we dont have to worry about precomputing every combination of flavors
        chacovol_denom=sparse.csr_matrix(Aconnsum.sum(axis=0)+sparse.triu(Aconnsum,k=1).sum(axis=1).T)
        chacovol_denom.eliminate_zeros()
        chacofile_subj=tmpdir+'/chacovol_denom_subj%05d.npz' % (isubj)
        sparse.save_npz(chacofile_subj,chacovol_denom,compressed=False)
    
    if Psparse_list:
        for iparc, Pdict in enumerate(Psparse_list):
            if isinstance(Pdict['transform'],list):
                #stored as csc to need to transpose
                Psparse=Pdict['transform'][isubj].tocsr()
            else:
                Psparse=Pdict['transform']
            
            chacoconn_parc=Psparse.T.tocsr() @ chacoconn @ Psparse
            
            #Make parcellated/downsampled outputs upper triangular (keeping diagonal)
            chacoconn_parc=sparse.triu(chacoconn_parc,k=0)+sparse.tril(chacoconn_parc,k=-1).T
               
            
            #sparse.save_npz(chacofile_subj,chacoconn.multiply(Aconnsum),compressed=False)
            chacofile_subj=tmpdir+'/chacoconn_parc%05d_subj%05d.npz' % (iparc,isubj)
            sparse.save_npz(chacofile_subj,chacoconn_parc,compressed=False)

            #chacovol_parc=((T_allsubj[isubj,:]>0) @ (B @ Psparse)).multiply(Asum[isubj,:] @ Psparse))
            
            #kval=0 means keep self-self entries (pairwise diagonals) when computing regional scores
            #kval=1 means remove that diagonal before computing regional score
            #pairwise (chacoconn) outputs remain unchanged
            chacovol_keepdiag_kval=1 #exclude diag by default
            if Pdict['keepdiag']:
                chacovol_keepdiag_kval=0
            
            chacovol_parc=sparse.csr_matrix(sparse.triu(chacoconn_parc,k=chacovol_keepdiag_kval).sum(axis=0)+sparse.triu(chacoconn_parc,k=1).sum(axis=1).T)
            chacovol_parc.eliminate_zeros()
            
            chacofile_subj=tmpdir+'/chacovol_parc%05d_subj%05d.npz' % (iparc,isubj)
            sparse.save_npz(chacofile_subj,chacovol_parc,compressed=False)

            if do_compute_denom:
                Aconnsum_parc=Psparse.T.tocsr() @ Aconnsum @ Psparse
                Aconnsum_parc.eliminate_zeros()
                #Make parcellated/downsampled outputs upper triangular (keeping diagonal)
                Aconnsum_parc=sparse.triu(Aconnsum_parc,k=0)+sparse.tril(Aconnsum_parc,k=-1).T
                chacofile_subj=tmpdir+'/chacoconn_parc%05d_denom_subj%05d.npz' % (iparc,isubj)
                sparse.save_npz(chacofile_subj,Aconnsum_parc,compressed=False)
                chacovol_parc_denom=sparse.csr_matrix(sparse.triu(Aconnsum_parc,k=chacovol_keepdiag_kval).sum(axis=0)+sparse.triu(Aconnsum_parc,k=1).sum(axis=1).T)
                chacovol_parc_denom.eliminate_zeros()
                
                chacofile_subj=tmpdir+'/chacovol_parc%05d_denom_subj%05d.npz' % (iparc,isubj)
                sparse.save_npz(chacofile_subj,chacovol_parc_denom,compressed=False)

###########################################################

def parcellation_to_volume(parcdata, parcvol):
    parcmask=parcvol!=0
    uparc,uparc_idx=np.unique(parcvol[parcmask],return_inverse=True)
    
    if parcdata.shape[0] == len(uparc):
        pass
    elif parcdata.shape[1] == len(uparc):
        parcdata=parcdata.T
    elif parcdata.shape[0] >= max(uparc):
        #this happens if input is cifti91k (full 0-91282) and parcvol does not have all of those indices
        parcdata=parcdata[uparc.astype(np.uint32)-1,:]
    elif parcdata.shape[1] >= max(uparc):
        #this happens if input is cifti91k (full 0-91282) and parcvol does not have all of those indices
        parcdata=parcdata[:,uparc.astype(np.uint32)-1].T
    else:
        print("Parcellated data dimensions do not match parcellation")
        return None
    
    newvol=np.zeros(parcvol.shape)
    newvol[parcmask]=np.mean(parcdata[uparc_idx],axis=1)
    
    return newvol
    
def make_triangular_matrix_symmetric(m):
    has_triu=np.any(np.triu(m!=0,1))
    has_tril=np.any(np.tril(m!=0,-1))
    if has_triu and not has_tril:
        m+=np.triu(m,1).T
    elif has_tril and not has_triu:
        m+=np.tril(m,-1).T
    return m

def save_chaco_output(chaco_output, delete_files=True):   
    #externals: Psparse_list, NUMBER_OF_SUBJECTS_TO_COMPUTE, tmpdir, Asum, Aconnsum, do_debug, outputbase, 
    #for chaco_output in chaco_output_list:
    #print(chaco_output)
    chaco_allsubj=[]
    chaco_denom_allsubj=[]
    
    do_nonzero_denom=False
    nonzero_denom_thresh=None
    if 'only_nonzero_denom' in chaco_output and chaco_output['only_nonzero_denom']:
        do_nonzero_denom=True
    if 'nonzero_denom_thresh' in chaco_output:
        nonzero_denom_thresh=chaco_output['nonzero_denom_thresh']
    
    Psparse=None
    output_reshape=chaco_output['reshape']
    if chaco_output['parcelindex'] is not None:
        Psparse=Psparse_list[chaco_output['parcelindex']]['transform']
            
    starttime_accum=time.time()
    #for isubj in range(numsubj):
    for isubj in range(NUMBER_OF_SUBJECTS_TO_COMPUTE):
        chacofile_subj=tmpdir+'/'+chaco_output['numerator'] % (isubj)
        chacofile_subj_denom=None
        chaco_numer=sparse.load_npz(chacofile_subj)
        
        if isinstance(Psparse,list):
            Ptmp=Psparse[isubj].tocsr()
        else:
            Ptmp=Psparse
            
        if chaco_output['denominator'] == 'Asum':
            if Ptmp is None:
                chaco_denom=Asum[isubj,:]
            else:
                chaco_denom=Asum[isubj,:] @ Ptmp
            #DON'T zero the denominator when numer is zero, because
            #we need the original denominator intact for nemoSC
            #chaco_denom = chaco_denom.multiply(chaco_numer>0)
            chaco_denom.eliminate_zeros()
        
        elif chaco_output['denominator'] == 'Aconnsum':
            if Ptmp is None:
                chaco_denom=Aconnsum[isubj]
            else:
                chaco_denom=Ptmp.T.tocsr() @ Aconnsum[isubj] @ Ptmp
            #DON'T zero the denominator when numer is zero, because
            #we need the original denominator intact for nemoSC
            #chaco_denom = chaco_denom.multiply(chaco_numer>0)
            chaco_denom.eliminate_zeros()
        
        else:
            chacofile_subj_denom=tmpdir+'/'+chaco_output['denominator'] % (isubj)
            chaco_denom=sparse.load_npz(chacofile_subj_denom)
        
        chaco_denom_allsubj.append(chaco_denom.copy())
        
        chaco_denom.data=1/chaco_denom.data.astype(np.float32)
        chaco_allsubj.append(chaco_numer.multiply(chaco_denom))
        
        if delete_files:
            os.remove(chacofile_subj)
            if chacofile_subj_denom is not None:
                os.remove(chacofile_subj_denom)
        
    if do_debug:
        print('Loading in %s took %s' % (chaco_output['name'],durationToString(time.time()-starttime_accum)))
    
    # if do_nonzero_denom:
    #   in this mode, for each voxel/parcel/pairwise connection, we compute the chaco ratio (lesion streamlines / total streamlines), 
    #   but IGNORE subjects that have 0 streamlines in the denominator for that location
    # else:
    #   in standard mode, we compute the chaco ratio for each location (lesion streamlines/total streamlines) for each subject and simply average across subjects
    #   If a subject does not have any streamlines in a location (denom = total streamlines=0), their chaco ratio for that location = 0
    #   and this 0 is included in the average across all subjects
    
    #generate an output that gives the fraction of subjects for which the denominator was non-zero
    #this can be used to mask the chacomean output to exclude regions with inconsistent denominators
    chacomean_denom_binfrac=None
    
    #   compute mean and stdev of chaco scores across all reference subjects
    if chaco_allsubj[0].shape[0] == 1:
        #stackable (for 1D chacovol)
        chaco_allsubj=sparse.vstack(chaco_allsubj)
        chaco_denom_allsubj=sparse.vstack(chaco_denom_allsubj)
        if do_nonzero_denom:
            chaconzd_numer=np.array(np.sum(chaco_allsubj,axis=0))
            chaconzd_denom=np.array(np.sum(chaco_denom_allsubj>0,axis=0))
            chaconzd_sqnumer=np.array(np.sum(chaco_allsubj.multiply(chaco_allsubj),axis=0))
            chaconzd_mask=(chaconzd_numer>0) & (chaconzd_denom>0)
            chaconzd_mean=np.zeros_like(chaconzd_numer)
            chaconzd_sqmean=np.zeros_like(chaconzd_numer)
            chaconzd_mean[chaconzd_mask]=chaconzd_numer[chaconzd_mask]/chaconzd_denom[chaconzd_mask]
            chaconzd_sqmean[chaconzd_mask]=chaconzd_sqnumer[chaconzd_mask]/chaconzd_denom[chaconzd_mask]
            chaconzd_std=np.sqrt(np.clip(chaconzd_sqmean-chaconzd_mean**2,0,None))
            
            chacomean_denom_binfrac=chaconzd_denom/chaco_allsubj.shape[0]
            chacomean=chaconzd_mean
            chacostd=chaconzd_std
        else:
            chacomean=np.array(np.mean(chaco_allsubj,axis=0))
            chacostd=np.sqrt(np.clip(np.array(np.mean(chaco_allsubj.multiply(chaco_allsubj),axis=0) - chacomean**2),0,None))
    else:
        #non-stackable (for list of 2D chacoconn)
        chacomean=0
        chacosqmean=0
        
        for ch in chaco_allsubj:
            chacomean+=ch
            chacosqmean+=ch.multiply(ch)
        
        if do_nonzero_denom:
            denom=0
            for chd in chaco_denom_allsubj:
                denom+=(chd>0).astype(np.float32)
            chacomean_denom_binfrac=denom/len(chaco_denom_allsubj)
            #need to invert the denom to use .multiply for element-wise division
            denom.data=1.0/denom.data
            chacomean=chacomean.multiply(denom)
            chacosqmean=chacosqmean.multiply(denom)
        else:
            chacomean/=len(chaco_allsubj)
            chacosqmean/=len(chaco_allsubj)
        
        chacostd=chacosqmean - chacomean.multiply(chacomean)
        chacostd[chacostd<0]=0
        chacostd.eliminate_zeros()
        chacostd=np.sqrt(chacostd)
    
        
    #this sqrt can be negative sometimes!
    #assuming it's just a numerical precision thing and set it to 0
    if sparse.issparse(chacostd):
        chacostd.data[np.isnan(chacostd.data)]=0
    else:
        chacostd[np.isnan(chacostd)]=0
    
    #threshold the chacomean by denom_binfrac if threshold is provided
    if chacomean_denom_binfrac is not None and nonzero_denom_thresh is not None and nonzero_denom_thresh>0:
        chacomean=chacomean.multiply(chacomean_denom_binfrac>nonzero_denom_thresh)
        chacostd=chacostd.multiply(chacomean_denom_binfrac>nonzero_denom_thresh)
        
    outfile_pickle=outputbase+'_'+chaco_output['name']+"_allref.pkl"
    pickle.dump(chaco_allsubj, open(outfile_pickle,"wb"))
    
    outfile_pickle=outputbase+'_'+chaco_output['name']+"_allref_denom.pkl"
    pickle.dump(chaco_denom_allsubj,open(outfile_pickle,"wb"))
    
    if output_reshape is None:
        pickle.dump(chacomean, open(outputbase+'_'+chaco_output['name']+'_mean.pkl', "wb"))
        pickle.dump(chacostd, open(outputbase+'_'+chaco_output['name']+'_stdev.pkl', "wb"))
        if chacomean_denom_binfrac is not None:
            pickle.dump(chacomean_denom_binfrac, open(outputbase+'_'+chaco_output['name']+'_denomfrac.pkl', "wb"))
    else:
        outimg=nib.Nifti1Image(np.reshape(np.array(chacomean),output_reshape.shape),affine=output_reshape.affine, header=output_reshape.header)
        nib.save(outimg,outputbase+'_%s_mean.nii.gz' % (chaco_output['name']))
        
        outimg=nib.Nifti1Image(np.reshape(np.array(chacostd),output_reshape.shape),affine=output_reshape.affine, header=output_reshape.header)
        nib.save(outimg,outputbase+'_%s_stdev.nii.gz' % (chaco_output['name']))
        
        if chacomean_denom_binfrac is not None:
            outimg=nib.Nifti1Image(np.reshape(np.array(chacomean_denom_binfrac),output_reshape.shape),affine=output_reshape.affine, header=output_reshape.header)
            nib.save(outimg,outputbase+'_%s_denomfrac.nii.gz' % (chaco_output['name']))
        
    if do_debug:
        print('Saving %s took %s' % (chaco_output['name'],durationToString(time.time()-starttime_accum)))

############################################################
############################################################
############################################################

# main command-line interface 

if __name__ == "__main__":
    args=argument_parse(sys.argv[1:])
    
    if args.continuous_value:
        args.cumulative=True
    
    lesionfile=args.lesion
    outputbase=args.outputbase
    chunklistfile=args.chunklist
    chunkdir=args.chunkdir
    refimgfile=args.refvol
    endpointfile=args.endpoints
    endpointmaskfile=args.endpointsmask
    asumfile=args.asum
    asumweightedfile=args.asum_weighted
    asumcumfile=args.asum_cumulative
    asumweightedcumfile=args.asum_weighted_cumulative
    trackweightfile=args.trackweights
    do_weighted=args.weighted
    do_smooth=args.smoothed
    smoothing_fwhm=args.smoothfwhm
    smoothing_mode=args.smoothmode
    s3nemoroot=args.s3nemoroot
    parcelfiles=args.parcelvol
    new_resolution=args.resolution
    tracklengthfile=args.tracklengths
    do_cumulative_hits=args.cumulative
    do_pairwise=args.pairwise
    do_continuous=args.continuous_value
    do_debug=args.debug
    debug_subjcount=args.subjcount
    tracking_algorithm=args.tracking_algorithm
    do_only_include_nonzero_subjects=args.only_nonzero_denom
    
    print("Executed with the following inputs:")
    for k,v in vars(args).items():
        if v is None:
            #assume unspecified
            continue
        if v is False:
            #assume store_true was unspecified
            continue
        if v is True:
            #assume store_true
            print("--%s" % (k))
            continue
        if isinstance(v,list):
            for vv in v:
                print("--%s" % (k), vv)
            continue
        print("--%s" % (k), v)
    print("")
    
    do_force_redownload = False
    do_download_nemofiles = False
    
    do_save_fullvol = False
    do_save_fullconn = False
    do_compute_denom = True
    
    if do_weighted:
        if do_cumulative_hits:
            asumfile=asumweightedcumfile
        else:
            asumfile=asumweightedfile
    else:
        if do_cumulative_hits:
            asumfile=asumcumfile
        else:
            asumfile=asumfile
            
    if s3nemoroot:
        do_download_nemofiles = True
        s3nemoroot=s3nemoroot.replace("s3://","").replace("S3://","")
        s3nemoroot_bucket=s3nemoroot.split("/")[0]
        s3nemoroot_prefix="/".join(s3nemoroot.split("/")[1:])
        if s3nemoroot_prefix:
            s3nemoroot_prefix+="/"
    
    if do_download_nemofiles:
        starttime_download_nemofiles=time.time()
    
        nemofiles_to_download=[asumfile]
        if do_weighted:
             #nemofiles_to_download=['nemo_Asum_weighted_endpoints.npz','nemo_siftweights.npy']
             nemofiles_to_download.extend([trackweightfile])
    
        if do_cumulative_hits:
            nemofiles_to_download.extend([tracklengthfile])
        
        if endpointmaskfile:
            nemofiles_to_download.extend([endpointmaskfile])
        #nemofiles_to_download.extend(['nemo_endpoints.npy','nemo_chunklist.npz',refimgfile])
        nemofiles_to_download.extend([endpointfile,chunklistfile,refimgfile])
    
        #check if we've already downloaded them (might be a multi-file run)
        if not do_force_redownload:
            nemofiles_to_download=[f for f in nemofiles_to_download if not os.path.exists(f)]
    
        if len(nemofiles_to_download) > 0:
            print('Downloading NeMo data files', end='', flush=True)
            num_cpu=multiprocessing.cpu_count()
            multiproc_cores=num_cpu-1
            P=multiprocessing.Pool(multiproc_cores, s3initialize)
    
            jobs = [(s3nemoroot_bucket,s3nemoroot_prefix+k.split("/")[-1],k) for k in nemofiles_to_download]
            try:
                P.map(s3download,jobs)
            except Exception as e:
                print('Download failed:',e)
                P.terminate()
                P.close()
                sys.exit(1)
            P.close()
    
            print(' took %.3f seconds' % (time.time()-starttime_download_nemofiles))
    
    try:
        smoothing_fwhm=float(smoothing_fwhm)
    except ValueError:
        do_smooth=False
        smoothing_fwhm=0.
    
    if smoothing_fwhm <= 0:
        do_smooth=False
    
    outputdir=Path(outputbase).parent.as_posix()
    outputbase_file=Path(outputbase).name
    
    print('Lesion file: %s' % (lesionfile))
    print('Output basename: %s' % (outputbase))
    print('Track weighting: ', do_weighted)
    print('Cumulative track hits: ', do_cumulative_hits)
    print('Continuous-valued lesion volume: ', do_continuous)
    print('Output pairwise connectivity: ', do_pairwise)
    print('Only include non-zero denom subjectcs: ', do_only_include_nonzero_subjects)
    
    starttime=time.time()
    
    
    chunklist=np.load(chunklistfile)
    volshape=chunklist['volshape']
    chunksize=chunklist['chunksize']
    chunkidx_flat=chunklist['chunkidx_flat']
    subjects=chunklist['subjects']
    numtracks=chunklist['numtracks']
    unique_chunks=chunklist['unique_chunks']
    
    refimg=nib.load(refimgfile)
    
    Limg=nib.load(lesionfile)
    
    expected_shape=(182,218,182)
    expected_shape_spm=(181,217,181)
    
    Limg = checkVolumeShape(Limg, refimg, lesionfile.split("/")[-1], expected_shape, expected_shape_spm)
    Ldata=Limg.get_fdata()
    Ldata[np.isnan(Ldata)]=0 #make sure there aren't any nans that throw off mask creation
    
    voxmm=np.sqrt(Limg.affine[:3,0].dot(Limg.affine[:3,0]))
    
    Ldata_max=np.max(np.abs(Ldata))
    if Ldata_max != 0:
        Ldata=Ldata/Ldata_max #this will be useful if we do a continuous-valued version later
    else:
        raise(Exception('Input lesion mask is all zeros!'))
    
    if do_continuous:
        Ldata=Ldata.astype(np.float32)
    else:
        #remember to change nemo_save_average_glassbrain.py --binarize option if we change this!
        Ldata=Ldata!=0
        
    Lmask=Ldata.flatten()
    
    ##################
    Psparse_list=[]
    
    origvoxmm=1
    origres_name="res%dmm" % (origvoxmm)
    
    if new_resolution:
        volshape=refimg.shape
        for r in new_resolution:
            r_pairwise=do_pairwise
            r_keepdiag=False
            if r.find("?") >= 0:
                #handle ?nopairwise option
                r_opts=r.split("?")[1:]
                r=r.split("?")[0]
                if "nopairwise" in r_opts:
                    r_pairwise=False
                if "keepdiag" in r_opts:
                    r_keepdiag=True
            if r.find("=") >= 0:
                [r,rname]=r.split("=")
                newvoxmm=round(abs(float(r)))
            else:
                newvoxmm=round(abs(float(r)))
                rname="res%dmm" % (newvoxmm)
        
            r_pairwisestr=""
            if r_pairwise:
                r_pairwisestr=" with pair-wise chacoconn"
            if r_keepdiag:
                r_pairwisestr+=", including diagonal in voxel-wise chacovol"
            
            if newvoxmm <= 1:
                do_save_fullvol=True
                do_save_fullconn=r_pairwise
                if rname:
                    origres_name=rname
                print('Output will include resolution %.1fmm (volume dimensions = %dx%dx%d)%s.' % (newvoxmm,volshape[0],volshape[1],volshape[2],r_pairwisestr))
                continue
        
            Psparse, newvolshape, newrefimg = createSparseDownsampleParcellation(newvoxmm, origvoxmm, volshape, refimg)
        
            Psparse_list.append({'transform': Psparse, 'reshape': newrefimg, 'voxmm': newvoxmm, 'name': rname, 'pairwise': r_pairwise, 'displayvol': None, 'keepdiag': r_keepdiag})
            
            print('Output will include resolution %.1fmm (volume dimensions = %dx%dx%d)%s.' % (newvoxmm,newvolshape[0],newvolshape[1],newvolshape[2],r_pairwisestr))
    
    if parcelfiles:
        for p in parcelfiles:
            p_pairwise=do_pairwise
            p_keepdiag=False
            p_displayvol=None
            p_numroi=None
            if p.find("?") >= 0:
                #handle ?nopairwise option
                p_opts=p.split("?")[1:]
                p=p.split("?")[0]
                if "nopairwise" in p_opts:
                    p_pairwise=False
                if "keepdiag" in p_opts:
                    p_keepdiag=True
                if any([x.startswith("displayvol=") for x in p_opts]):
                    displayvolfile=[x.split("=")[1] for x in p_opts if x.startswith("displayvol=")][0]
                    p_displayvol=nib.load(displayvolfile)
                if any([x.startswith("numroi=") for x in p_opts]):
                    p_numroi_str=[x.split("=")[1] for x in p_opts if x.startswith("numroi=")][0]
                    try:
                        p_numroi=int(p_numroi_str)
                    except ValueError:
                        p_numroi=None
            if p.find("=") >= 0:
                [pfile,pname]=p.split("=")
            else:
                pfile=p
                pname="parc%05d" % (len(Psparse_list))
            
            if(pfile.lower().endswith(".npz")):
                dostart=time.time()
                Psparse_allsubj=sparse.load_npz(pfile)
                numroisubj=Psparse_allsubj.shape[0]
            
                max_seq_roi_val=Psparse_allsubj.max()
                if p_numroi is not None:
                    max_seq_roi_val=np.array(p_numroi)
                #store these as csc for memory efficiency (have to convert each subject later)
                def flat2sparse(isubj):
                    return flatParcellationToTransform(Psparse_allsubj, isubj, out_type="csc", max_sequential_roi_value=max_seq_roi_val)
            
                num_cpu=multiprocessing.cpu_count()
                multiproc_cores=num_cpu-1
                P=multiprocessing.Pool(multiproc_cores)
                Psparse=P.map(flat2sparse,range(numroisubj))
                P.close()
            
                Psparse_allsubj=None
             
                numroi=Psparse[0].shape[1]
                
            elif(pfile.lower().endswith(".pkl")):
                #this file type assumes a list of voxel x ROI Psparse transform matrices
                Psparse=pickle.load(open(pfile,"rb"))
                numroisubj=len(Psparse)
                numroi=Psparse[0].shape[1]
                numvoxels=Psparse[0].shape[0]
                
            else:
                Pimg=nib.load(pfile)
                Pimg = checkVolumeShape(Pimg, refimg, pfile.split("/")[-1], expected_shape, expected_shape_spm)
                Pdata=Pimg.get_fdata()
            
                max_seq_roi_val=None
                if p_numroi is not None:
                    max_seq_roi_val=np.array(p_numroi)
                
                Psparse = flatParcellationToTransform(Pdata.flatten(), None, out_type="csr", max_sequential_roi_value=max_seq_roi_val)
                numroi = Psparse.shape[1]
            
            
            Psparse_list.append({'transform': Psparse, 'reshape': None, 'voxmm': None, 'name': pname, 'pairwise': p_pairwise, 'displayvol': p_displayvol, 'keepdiag': p_keepdiag})
        
            p_pairwisestr=""
            if p_pairwise:
                p_pairwisestr=" with pair-wise chacoconn"
            if p_keepdiag:
                p_pairwisestr+=", include diagonal in region-wise chacovol"
            
            if isinstance(Psparse,list):
                print('Output will include subject-specific parcellation %s (%s, total parcels = %d)%s.' % (pname,pfile.split("/")[-1],numroi,p_pairwisestr))
            else:
                print('Output will include parcellation %s (%s, total parcels = %d)%s.' % (pname,pfile.split("/")[-1],numroi,p_pairwisestr))
            
    #if parcelfiles_subject_specific:
    #    for p in parcelfiles_subject_specific:
            #250MB for 20 subjects as a 20x7M sparse matrix. would be 5GB for 420 subjects. only 48MB for 20subj compressed, so 1GB
            #120MB for 50subj compressed
            #130MB for 50subj UNCOMPRESSED when we masked by endpoints! = 1GB for 420 subjects
            #Pdata=
    
    if len(Psparse_list)==0:
        Psparse_list=None
    
    ##################
    
    chunks_in_lesion=np.unique(chunkidx_flat[Lmask!=0])
    print('Total voxels in lesion mask: %d' % (np.sum(Lmask!=0)))
    print('Total chunks in lesion mask: %d' % (len(chunks_in_lesion)))
    missing_chunks=set(chunks_in_lesion)-set(unique_chunks)
    if len(missing_chunks) > 0:
        chunks_to_load=list(set(chunks_in_lesion) - missing_chunks)
        print('Lesion includes %d chunks outside reference white-matter volume' % (len(missing_chunks)))
        print('Total white-matter chunks in lesion mask: %d' % (len(chunks_to_load)))
    else:
        chunks_to_load=chunks_in_lesion
    
    totalchunkbytes=np.sum(chunklist['chunkfilesize'][chunks_to_load])
    totalchunkbytes_string=""
    if totalchunkbytes >= 1024*1024*1024:
        totalchunkbytes_string='%.2f GB' % (totalchunkbytes/(1024*1024*1024))
    else:
        totalchunkbytes_string='%.2f MB' % (totalchunkbytes/(1024*1024))
    print('Total size for all %d chunk files: %s' % (len(chunks_to_load),totalchunkbytes_string))
    
    chunkfile_fmt=chunkdir+'/chunk%05d.npz'
    os.makedirs(chunkdir,exist_ok=True)
    
    if do_download_nemofiles:
        chunkfiles_to_download=[chunkdir+'/chunk%05d.npz' % (x) for x in chunks_to_load]
        if do_force_redownload:
            totalchunkbytes_download_string=totalchunkbytes_string
        else:
            chunks_to_download=[i for i,f in zip(chunks_to_load,chunkfiles_to_download) if not os.path.exists(f)]
            chunkfiles_to_download=[chunkdir+'/chunk%05d.npz' % (x) for x in chunks_to_download]
            
            totalchunkbytes_download=np.sum(chunklist['chunkfilesize'][chunks_to_download])
            totalchunkbytes_download_string=""
            if totalchunkbytes_download >= 1024*1024*1024:
                totalchunkbytes_download_string='%.2f GB' % (totalchunkbytes_download/(1024*1024*1024))
            else:
                totalchunkbytes_download_string='%.2f MB' % (totalchunkbytes_download/(1024*1024))
        
        if len(chunkfiles_to_download) > 0:
            print('Downloading %d chunks (%s)' % (len(chunkfiles_to_download), totalchunkbytes_download_string), end='', flush=True)
            starttime_download_chunks=time.time()
            num_cpu=multiprocessing.cpu_count()
            multiproc_cores=num_cpu-1
            P=multiprocessing.Pool(multiproc_cores, s3initialize)
            
            #make sure chunk file includes the directory from the input (eg: /chunkfiles/ or /chunkfiles_<algo>/
            jobs = [(s3nemoroot_bucket,s3nemoroot_prefix+"/".join(k.split("/")[-2:]),k) for k in chunkfiles_to_download]
            P.map(s3download,jobs)
            P.close()
            
            print(' took %s' % (durationToString(time.time()-starttime_download_chunks)))
    
    numsubj=len(subjects)
    numvoxels=chunkidx_flat.size
    
    #have to create this before running tempfile.mkdtemp()
    os.makedirs(outputdir,exist_ok=True)
    
    #tmpdir=outputbase+'_tmp'
    #note: need to set dir explicitly in case we didn't have a "/" or "." in front of output path
    #(then it will assume /tmp)
    tmpdir=tempfile.mkdtemp(prefix=outputbase_file+'_tmp',dir=outputdir)
    tmpchunkfile_fmt=tmpdir+'/tmpsubj_chunk%05d.npz'
    
    #os.makedirs(tmpdir,exist_ok=True)
    
    #original:
    #Track hits for 23 chunks took 21.996 seconds on 15 threads
    #Merging track hits from 23 chunks took 0.562 seconds
    #Loading sumfiles took 3.669 seconds
    #Loading sumfiles and endpoints took 4.223 seconds
    #Mapping to endpoints and ChaCo took 2.208 seconds on 15 threads
    #Mapping to conn  took 2.395 seconds on 15 threads
    
    #after doing eliminate_zeros() inside loop
    #Track hits for 23 chunks took 22.370 seconds on 15 threads
    #Merging track hits from 23 chunks took 0.558 seconds
    #Loading sumfiles took 3.640 seconds
    #Loading sumfiles and endpoints took 4.196 seconds
    #Mapping to endpoints and ChaCo took 2.194 seconds on 15 threads
    #Mapping to conn  took 2.404 seconds on 15 threads
    
    ###########################################################
    
    ###########################################################
    
    num_cpu=multiprocessing.cpu_count()
    multiproc_cores=num_cpu-1
    P=multiprocessing.Pool(multiproc_cores)
    
    print('Track hits for %d chunks' % (len(chunks_to_load)), end='', flush=True)
    starttime_lesionchunks=time.time()
    
    chunks_to_load_success=P.map(save_lesion_chunk,chunks_to_load)
    P.close()
    
    print(' took %s on %d threads' % (durationToString(time.time()-starttime_lesionchunks),multiproc_cores))
    #total files for this 376-chunk lesion = 699MB
    
    
    #now sum up the track hit maps for all chunks
    #result = (numsubj x numtracks)
    starttime_sum=time.time()
    
    #P=multiprocessing.Pool(multiproc_cores)
    #T_allsubj=P.map(sparse.load_npz,[tmpchunkfile_fmt % (whichchunk) for whichchunk in chunks_to_load])
    #P.close()
    #T_allsubj=sum(T_allsubj)
    #print(type(T_allsubj))
    #print(T_allsubj.shape)
    
    T_allsubj=None
    
    print('Merging track hits from %d chunks' % (len(chunks_to_load)), end='', flush=True)
    #this took almost exactly the same amount of time as the Pool version! (350 seconds for big 375chunk lesion)
    for ich,whichchunk in enumerate(chunks_to_load):
        tmpfilename=tmpchunkfile_fmt % (whichchunk)
        Tchunk=sparse.load_npz(tmpfilename)
        if T_allsubj is None:
            T_allsubj=Tchunk
        else:
            T_allsubj+=Tchunk
        os.remove(tmpfilename)
    print(' took %s' % (durationToString(time.time()-starttime_sum)))
    
    
    ##############
    #without predownloading:
    #Loading sumfiles took 276.461 seconds
    #Loading sumfiles and endpoints took 277.108 seconds
    
    starttime_loadmap=time.time()
    #part 2
    Asum=sparse.load_npz(asumfile)
    if do_weighted:
        trackweights=np.load(trackweightfile,mmap_mode='r')
    else:
        trackweights=None
    
    if do_cumulative_hits:
        tracklengths=np.load(tracklengthfile,mmap_mode='r')
        #Asum should be something like:
        #we use Asum even if we did "compute denom" below
        #and right now the Asum assumes single hit per track
        #Also!!!!! need to add Psparse to map_to_endpoints_numerator
        #B=sparse.csr_matrix(sparse.csr_matrix((tracklengths[isubj,tidx],(tidx,endpt)),shape=(numtracks,numvoxels)).sum(axis=0))
    else:
        tracklengths=None
    
    print('Loading sumfiles took %s' % (durationToString(time.time()-starttime_loadmap)))
    
    #need this in the denominator
    #also make sure the non-weighted Asum (int32) gets cast as float32
    #(otherwise it creates a float64)
    #Asum.data=1/Asum.data.astype(np.float32)
    
    if endpointmaskfile:
        endpointmat=np.load(endpointfile)
        endpointmask=np.load(endpointmaskfile)
        print("Masking endpoints with input mask file %s" % (endpointmaskfile))
        if endpointmask.shape[0]==endpointmat.shape[0]//2:
            endpointmat*=np.vstack((endpointmask,endpointmask))
        elif endpointmask.shape[0]==endpointmat.shape[0]:
            endpointmat*=endpointmask
        else:
            raise(Exception('Invalid endpointmask shape! Must be %d or %d, but was instead %d' % (endpointmat.shape[0]//2,endpointmat.shape[0],endpointmask.shape[0])))
    else:
        endpointmask=None
        endpointmat=np.load(endpointfile,mmap_mode='r')
    
    print('Loading sumfiles and endpoints took %s' % (durationToString(time.time()-starttime_loadmap)))
    
    tidx=np.append(np.arange(numtracks),np.arange(numtracks))
    tidx1=np.arange(numtracks)
    
    
    print('Mapping to endpoints and ChaCo', end='',flush=True)
    
    if debug_subjcount and debug_subjcount>0:
        NUMBER_OF_SUBJECTS_TO_COMPUTE=min(debug_subjcount,numsubj)
    else:
        NUMBER_OF_SUBJECTS_TO_COMPUTE=numsubj
    
    #Now multiply with B mat to go from tracks->endpoints
    #result = (numsubj x numvoxels)
    starttime_endpoints=time.time()
    
    if do_pairwise:
        if do_debug:
            print(' (conn)', end='',flush=True)
        
        #Now multiply with B mat to go from tracks->endpoints
        #result = (numsubj x numvoxels)
        starttime_endpoints=time.time()
        
        #multiproc_cores=1
        P=multiprocessing.Pool(multiproc_cores)
        #P.map(map_to_endpoints, range(numsubj))
        P.map(map_to_endpoints_conn, range(NUMBER_OF_SUBJECTS_TO_COMPUTE))
        
        P.close()
        
        print(' took %s on %d threads' % (durationToString(time.time()-starttime_endpoints),multiproc_cores))
        
    else:    
        if do_debug:
            print(' (voxelwise, not conn)', end='',flush=True)
        
        starttime_endpoints=time.time()
        
        #multiproc_cores=1
        P=multiprocessing.Pool(multiproc_cores)
        #P.map(map_to_endpoints_numerator, range(numsubj))
        P.map(map_to_endpoints_numerator, range(NUMBER_OF_SUBJECTS_TO_COMPUTE))
        
        P.close()
        
        #endpointmat=None
        
        print(' took %s on %d threads' % (durationToString(time.time()-starttime_endpoints),multiproc_cores))
    
    ########
    
    
    endpointmat=None
    trackweights=None
    tracklengths=None
    endpointmask=None
    
    if do_debug:
        print("Temp outputs in: ",tmpdir)
    
    ########
    
    #######################################################################
    #######################################################################
    #For each filetype, read all 420 and compute the chaco score (divide by denom)
    #save pickled list if requested
    #save mean
    #save std
    #1. read chacovol, divide by Asum
    #2. read chacoconn, divide by Asumconn or chacoconn_denom <--- Asumconn we talked about before was the sum across ALL subjects, so only useful for when we calc mean?
    #   - but really we should save a pickled version that contains the Asumconn for EACH subject.... we could then load this in
    #3. read chacovol_parc, divide by chacovol_denom_parc
    #4. read chacoconn_parc, divide by chacoconn_denom_parc
    
    
    #full conn, fs86, res2, res3
    #chacoconn = 12GB (*2=24GB with denom), fs86 = 2.2MB, res2=1.5GB (*2=3GB with denom), res3=500MB (*2 = 1GB with denom)
    #gzip chacoconn takes 1m25s, 12GB -> 47MB
    #gzip chacoconn_parc res2 -> 17s -> 28MB
    #gzip chacoconn_parc res3 -> 7s -> 21MB
    
    
    #Mapping to conn with small 3720 (all 420 subjects) took 3m16.995s on 15 threads, total run was 8m8 sec
    # - haven't tested using saved nemo_Aconnsum.npz yet (because it doesn't yet exist)
    #   4 minutes spent on running the output loop
    
    # With 5136 tracking hits and merging took 20 min, then mapping to conn took  4m43s
    # chacoconn = 16GB (*2 = 32GB with denom) (took 14 minutes)
    #   chacoconn_mean.pkl is 4.3GB GB
    # fs86 = 13MB (*2 = 26GB with denom) (took 0 minutes)
    # res2 = 5.7GB (*2 = 11.4GB with denom) (took 30 minutes)
    #   chacoconn_parc00001_mean.pkl is 2.3 GB
    # res3 = 4.1GB (*2 = 8.2GB with denom) (took 13 minutes)
    #   chacoconn_parc00002_mean.pkl is 1 GB
    # - takes a while.... uses single CPU but ~34% of memory (45GB) while doing each res 
    # total time = 84 minutes
    # total time for only 2mm and 3mm: 60 min
    
    # gzip chacoconn 4m30s: 16GB -> 1.8GB
    # gzip chacoconn_parc res2 took 4m15s: 5.7GB -> 1.3GB
    # gzip chacoconn_parc res3 took 4m11s: 4.1GB -> 979MB
    
    # haven't tested weighted
    # - chaco mean png looks a little different from the original version (that was probably siftweighted, and the non-siftweighted one was broken before)
    
    chaco_output_list=[]
    
    only_nonzero_denom_chacovol=do_only_include_nonzero_subjects
    only_nonzero_denom_chacoconn=do_only_include_nonzero_subjects
    
    if do_save_fullvol:
        chaco_output_list.append({"name":"chacovol_%s" % (origres_name), "numerator":'chacovol_subj%05d.npz', "denominator":'chacovol_denom_subj%05d.npz', 
            "parcelindex":None, "reshape": refimg, "voxmm": voxmm,"only_nonzero_denom":only_nonzero_denom_chacovol})
    
    if do_save_fullconn and do_pairwise:
        #chaco_output_list.append({"name":"chacoconn_%s" % (origres_name), "numerator":'chacoconn_subj%05d.npz', "denominator":'Aconnsum', 'parcelindex':None, 'reshape': None})
        chaco_output_list.append({"name":"chacoconn_%s" % (origres_name), 
            "numerator":'chacoconn_subj%05d.npz', 
            "denominator": 'chacoconn_denom_subj%05d.npz', 
            "parcelindex":None, "reshape": None, "displayvol": None,
            "only_nonzero_denom":only_nonzero_denom_chacoconn})
    
    if Psparse_list:
        for iparc in range(len(Psparse_list)):
            chaco_output_list.append({"name":"chacovol_%s" % (Psparse_list[iparc]['name']), 
                "numerator": 'chacovol_parc%05d_subj%%05d.npz' % (iparc), 
                "denominator": 'chacovol_parc%05d_denom_subj%%05d.npz' % (iparc), 
                "parcelindex":iparc, 
                "reshape": Psparse_list[iparc]['reshape'], 
                "voxmm": Psparse_list[iparc]['voxmm'],
                "displayvol": Psparse_list[iparc]['displayvol'],
                "only_nonzero_denom":only_nonzero_denom_chacovol})
            if Psparse_list[iparc]['pairwise']:
                chaco_output_list.append({"name":"chacoconn_%s" % (Psparse_list[iparc]['name']), 
                    "numerator": 'chacoconn_parc%05d_subj%%05d.npz' % (iparc), 
                    "denominator":'chacoconn_parc%05d_denom_subj%%05d.npz' % (iparc),
                    "parcelindex":iparc, "reshape": None, "displayvol": None, "pairwise": True,
                    "only_nonzero_denom":only_nonzero_denom_chacoconn})
    
    
    #chaco_output_list=[chaco_output_list[0]]
    
    #only use 2 cores since each chacoconn uses so much memory
    P=multiprocessing.Pool(3)
    #P.map(map_to_endpoints, range(numsubj))
    P.map(save_chaco_output,chaco_output_list)
    
    P.close()
    
    #save lesion glassbrain here so we have a record of the EXACT input used internally 
    imglesion_mni=nib.Nifti1Image(Ldata,affine=refimg.affine, header=refimg.header)
    imgfile_lesion=outputbase+'_glassbrain_lesion_orig.png'
    plotting.plot_glass_brain(imglesion_mni,output_file=imgfile_lesion,cmap='jet',colorbar=True)
    
    #os.rmdir(tmpdir)
    shutil.rmtree(tmpdir)
    
    ###
    
    if do_smooth:
        for chaco_output in chaco_output_list:
            if chaco_output['reshape'] is None:
                continue
            
            print('Smoothing individual %s volumes at FWHM=%.2fmm (Just to generate a pretty mean image)' % (chaco_output['name'], smoothing_fwhm))
            
            infile_pickle=outputbase+'_'+chaco_output['name']+"_allref.pkl"
            infile_denom_pickle=outputbase+'_'+chaco_output['name']+"_allref_denom.pkl"
            chaco_allsubj=pickle.load(open(infile_pickle,"rb"))
            
            if smoothing_mode == "counts":
                chaco_denom_allsubj=pickle.load(open(infile_denom_pickle,"rb"))
                chaco_allsubj=chaco_allsubj.multiply(chaco_denom_allsubj) #multiply the denom to get just numerator before smoothing
            
            #note: the non-sparse version of this runs in ~20 seconds on 16 core, but takes up 28MB*420=12GB temporarily
            def smoothfun_ratio(rowindex):
                return smooth_sparse_vol(chaco_allsubj[rowindex,:], smoothing_fwhm, chaco_output['reshape'].shape, chaco_output['voxmm'])
            
            def smoothfun_counts(rowindex):
                outsmooth_numer=smooth_sparse_vol(chaco_allsubj[rowindex,:], smoothing_fwhm, chaco_output['reshape'].shape, chaco_output['voxmm'])
                outsmooth_denom=smooth_sparse_vol(chaco_allsubj_denom[rowindex,:], smoothing_fwhm, chaco_output['reshape'].shape, chaco_output['voxmm'])
                
                outsmooth_denom = outsmooth_denom.multiply(outsmooth_numer>0)
                outsmooth_denom.eliminate_zeros()
                
                outsmooth_denom.data=1/outsmooth_denom.data
                outsmooth_numer=outsmooth_numer.multiply(outsmooth_denom)
                return outsmooth_numer
            
            
            
            P=multiprocessing.Pool(multiproc_cores)
            if smoothing_mode == "ratio":
                chaco_smooth=P.map(smoothfun_ratio, range(chaco_allsubj.shape[0]))
            elif smoothing_mode == "counts":
                chaco_smooth=P.map(smoothfun_counts, range(chaco_allsubj.shape[0]))
            P.close()
            
            chaco_smooth=sparse.vstack(chaco_smooth)
            chaco_smooth_mean=np.array(np.mean(chaco_smooth,axis=0))
            chaco_smooth_std=np.sqrt(np.array(np.mean(chaco_smooth.multiply(chaco_smooth),axis=0) - chaco_smooth_mean**2))
            #this sqrt can be negative sometimes!
            #assuming it's just a numerical precision thing and set it to 0
            if sparse.issparse(chaco_smooth_std):
                chaco_smooth_std.data[np.isnan(chaco_smooth_std.data)]=0
            else:
                chaco_smooth_std[np.isnan(chaco_smooth_std)]=0
            
            outimg=nib.Nifti1Image(np.reshape(np.array(chaco_smooth_mean),chaco_output['reshape'].shape),affine=chaco_output['reshape'].affine, header=chaco_output['reshape'].header)
            nib.save(outimg,outputbase+'_%s_smooth%gmm_mean.nii.gz' % (chaco_output['name'],smoothing_fwhm))
            
            outimg=nib.Nifti1Image(np.reshape(np.array(chaco_smooth_std),chaco_output['reshape'].shape),affine=chaco_output['reshape'].affine, header=chaco_output['reshape'].header)
            nib.save(outimg,outputbase+'_%s_smooth%gmm_stdev.nii.gz' % (chaco_output['name'],smoothing_fwhm))
            
    print('NeMo took a total of %s for %s' % (durationToString(time.time()-starttime),lesionfile))
