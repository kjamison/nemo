import multiprocessing
import os
from pathlib import Path 
import numpy as np
import nibabel as nib
import nibabel.processing
import time
import sys
from scipy import sparse
from nilearn import plotting, image
from scipy import ndimage
import argparse 
import tempfile
import subprocess
import boto3
import pickle
import shutil

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
    if out_type == "csr":
        return sparse.csr_matrix((np.ones(pmaskidx.size),(pmaskidx,uidx)),shape=(numvoxels,numroi),dtype=np.float32)
    elif out_type == "csc":
        return sparse.csc_matrix((np.ones(pmaskidx.size),(pmaskidx,uidx)),shape=(numvoxels,numroi),dtype=np.float32)
    
def checkVolumeShape(Pdata, filename_display, expected_shape, expected_shape_spm):
    if Pdata.shape == expected_shape:
        #seems correct
        pass
    elif Pdata.shape == expected_shape_spm:
        print('%s was 181x217x181, not the expected 182x218x181. Assuming SPM-based reg and padding end of each dim.' % (filename_display))
        Pdata=np.pad(Pdata,(0,1),mode='constant')
    else:
        raise(Exception('Unexpected volume size: (%d,%d,%d) for %s. Input must be registered to 182x218x182 MNIv6 template (FSL template)' % (Pdata.shape[0],Pdata.shape[1],Pdata.shape[2],filename_display)))
    return Pdata
        
parser=argparse.ArgumentParser(description='Read lesion mask and create voxel-wise ChaCo maps for all reference subjects')

parser.add_argument('--lesion','-l',action='store', dest='lesion')
parser.add_argument('--outputbase','-o',action='store', dest='outputbase')
parser.add_argument('--chunklist','-c',action='store', dest='chunklist')
parser.add_argument('--chunkdir','-cd',action='store', dest='chunkdir')
parser.add_argument('--refvol','-r',action='store', dest='refvol')
parser.add_argument('--endpoints','-e',action='store', dest='endpoints')
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
parser.add_argument('--debug',action='store_true', dest='debug')

args=parser.parse_args()

if args.continuous_value:
    args.cumulative=True
    
lesionfile=args.lesion
outputbase=args.outputbase
chunklistfile=args.chunklist
chunkdir=args.chunkdir
refimgfile=args.refvol
endpointfile=args.endpoints
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

exit(0)
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

    # make a per process s3_client
    s3_client = None
    def s3initialize():
        global s3_client
        s3_client = boto3.client('s3')

    def s3download(job):
        bucket, key, filename = job
        s3_client.download_file(bucket,key,filename)

if do_download_nemofiles:
    starttime_download_nemofiles=time.time()

    nemofiles_to_download=[asumfile]
    if do_weighted:
         #nemofiles_to_download=['nemo_Asum_weighted_endpoints.npz','nemo_siftweights.npy']
         nemofiles_to_download.extend([trackweightfile])
    
    if do_cumulative_hits:
        nemofiles_to_download.extend([tracklengthfile])
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
    
        jobs = [(s3nemoroot_bucket,s3nemoroot_prefix+'/'+k.split("/")[-1],k) for k in nemofiles_to_download]
        P.map(s3download,jobs)
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

Ldata=Limg.get_fdata()

voxmm=np.sqrt(Limg.affine[:3,0].dot(Limg.affine[:3,0]))

expected_shape=(182,218,182)
expected_shape_spm=(181,217,181)


Ldata = checkVolumeShape(Ldata, lesionfile.split("/")[-1], expected_shape, expected_shape_spm)

Ldata=Ldata/np.max(Ldata) #this will be useful if we do a continuous-valued version later
if do_continuous:
    Lmask=Ldata.flatten().astype(np.float32)
else:
    Lmask=Ldata.flatten()>0


##################
Psparse_list=[]

origvoxmm=1
origres_name="res%dmm" % (origvoxmm)

if new_resolution:

    volshape=refimg.shape
    for r in new_resolution:
        if r.find("=") >= 0:
            [r,rname]=r.split("=")
            newvoxmm=round(abs(float(r)))
        else:
            newvoxmm=round(abs(float(r)))
            rname="res%dmm" % (newvoxmm)
        
        if newvoxmm <= 1:
            do_save_fullvol=True
            do_save_fullconn=do_pairwise
            if rname:
                origres_name=rname
            print('Output will include resolution %.1fmm (volume dimensions = %dx%dx%d).' % (newvoxmm,volshape[0],volshape[1],volshape[2]))
            continue
        
        Psparse, newvolshape, newrefimg = createSparseDownsampleParcellation(newvoxmm, origvoxmm, volshape, refimg)
        
        Psparse_list.append({'transform': Psparse, 'reshape': newrefimg, 'voxmm': newvoxmm, 'name': rname})
        print('Output will include resolution %.1fmm (volume dimensions = %dx%dx%d).' % (newvoxmm,newvolshape[0],newvolshape[1],newvolshape[2]))

if parcelfiles:
    for p in parcelfiles:
        if p.find("=") >= 0:
            [pfile,pname]=p.split("=")
        else:
            pfile=p
            pname="parc%05d" % (len(Psparse_list))
            
        if(pfile.lower().endswith(".npz")):
            dostart=time.time()
            Psparse_allsubj=sparse.load_npz(pfile)
            numroisubj=Psparse_allsubj.shape[0]
            
            #store these as csc for memory efficiency (have to convert each subject later)
            def flat2sparse(isubj):
                return flatParcellationToTransform(Psparse_allsubj, isubj, out_type="csc")
            
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
            Pdata=nib.load(pfile).get_fdata()
            
            Pdata = checkVolumeShape(Pdata, pfile.split("/")[-1], expected_shape, expected_shape_spm)
    
            Psparse = flatParcellationToTransform(Pdata.flatten(), None, out_type="csr")
            numroi = Psparse.shape[1]
            
        Psparse_list.append({'transform': Psparse, 'reshape': None, 'voxmm': None, 'name': pname})
        
        if isinstance(Psparse,list):
            print('Output will include subject-specific parcellation %s (%s, total parcels = %d).' % (pname,pfile.split("/")[-1],numroi))
        else:
            print('Output will include parcellation %s (%s, total parcels = %d).' % (pname,pfile.split("/")[-1],numroi))

#if parcelfiles_subject_specific:
#    for p in parcelfiles_subject_specific:
        #250MB for 20 subjects as a 20x7M sparse matrix. would be 5GB for 420 subjects. only 48MB for 20subj compressed, so 1GB
        #120MB for 50subj compressed
        #130MB for 50subj UNCOMPRESSED when we masked by endpoints! = 1GB for 420 subjects
        #Pdata=

if len(Psparse_list)==0:
    Psparse_list=None

##################

#wmimg=nib.Nifti1Image(np.reshape(Lmask,Atest['nifti_volshape'][0]),affine=img.affine,header=img.header)
#plotting.view_img(wmimg,bg_img=img,cmap='hot')
#plotting.plot_glass_brain(wmimg,cmap='jet')

chunks_in_lesion=np.unique(chunkidx_flat[Lmask>0])
print('Total voxels in lesion mask: %d' % (np.sum(Lmask>0)))
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
    
        jobs = [(s3nemoroot_bucket,s3nemoroot_prefix+'/chunkfiles/'+k.split("/")[-1],k) for k in chunkfiles_to_download]
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
def save_lesion_chunk(whichchunk):
    subjchunksA=sparse.load_npz(chunkfile_fmt % (whichchunk))
    Lchunk=Lmask[chunkidx_flat==whichchunk]
    chunktrackmask=[]
    for isubj in range(numsubj):
        #binarize the T matrix (each streamline is hit or not) here
        #If we remove this, we have to figure out the denominator for ChaCo (currently Asum = total number of streamlines at each endpoint)
        if do_cumulative_hits:
            chunktrackmask.append(sparse.csr_matrix(Lchunk @ subjchunksA[(isubj*chunksize):((isubj+1)*chunksize),:]))
        else:
            chunktrackmask.append(sparse.csr_matrix(Lchunk @ subjchunksA[(isubj*chunksize):((isubj+1)*chunksize),:])>0)
        chunktrackmask[-1].eliminate_zeros()

    tmpfilename=tmpchunkfile_fmt % (whichchunk)
    sparse.save_npz(tmpfilename,sparse.vstack(chunktrackmask),compressed=False)
###########################################################

num_cpu=multiprocessing.cpu_count()
multiproc_cores=num_cpu-1
P=multiprocessing.Pool(multiproc_cores)

print('Track hits for %d chunks' % (len(chunks_to_load)), end='', flush=True)
starttime_lesionchunks=time.time()

P.map(save_lesion_chunk,chunks_to_load)
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

endpointmat=np.load(endpointfile,mmap_mode='r')

print('Loading sumfiles and endpoints took %s' % (durationToString(time.time()-starttime_loadmap)))

tidx=np.append(np.arange(numtracks),np.arange(numtracks))
tidx1=np.arange(numtracks)

#original:
#Mapping to endpoints and ChaCo took 4.252 seconds on 15 threads
#Mapping to conn  took 2.511 seconds on 15 threads

#now with T.eliminate_zeros() in map_to_endpoints() also:
#Mapping to endpoints and ChaCo took 2.222 seconds on 15 threads
#Mapping to conn  took 2.420 seconds on 15 threads
###########################################################
def map_to_endpoints(isubj):
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
    endpt=endpointmat[(isubj,isubj+numsubj),:]
    endpt1=endpt.min(axis=0)
    endpt2=endpt.max(axis=0)
    #any endpoints in "voxel 0" are from spurious endpoints for "lost" streamlines
    #but not this way! because then endpt and data and denoms don't line up!
    endpt_iszero=(endpt1==0) | (endpt2==0)
    #endpt1=endpt1[~endpt_iszero]
    #endpt2=endpt2[~endpt_iszero]
    #chacoconn=sparse.csr_matrix(((T_allsubj[isubj,:]>0).toarray().flatten(),(endpt1,endpt2)),shape=(numvoxels,numvoxels),dtype=np.float32)
    
    #note: need to cast to non-bool here otherwise the summing in sparse matrix build doesn't work!
    T=T_allsubj[isubj,:].astype(np.float32)
    if trackweights is not None:
        T.data*=trackweights[isubj,T.indices]
    #T[endpt_iszero]=0
    T.data[endpt_iszero[T.indices]]=0
    #T.eliminate_zeros()
    chacoconn=sparse.csr_matrix((T.data,(endpt1[T.indices],endpt2[T.indices])),shape=(numvoxels,numvoxels),dtype=np.float32)

    #sparse.save_npz(tmpdir+'/chacoconnAconnsum_subj%05d.npz' % (isubj),Aconnsum,compressed=False)
    
    
    chacovol=sparse.csr_matrix(chacoconn.sum(axis=0)+chacoconn.sum(axis=1).T) #.multiply(Asum[isubj,:])
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
        Aconnsum=sparse.csr_matrix((denom_val[T.indices],(endpt1[T.indices],endpt2[T.indices])),shape=(numvoxels,numvoxels),dtype=np.float32)
        Aconnsum.eliminate_zeros()
        if do_save_fullconn:
            chacofile_subj=tmpdir+'/chacoconn_denom_subj%05d.npz' % (isubj)
            sparse.save_npz(chacofile_subj,Aconnsum,compressed=False)
            
    if Psparse_list:
        for iparc, Pdict in enumerate(Psparse_list):
            if isinstance(Pdict['transform'],list):
                #stored as csc to need to transpose
                Psparse=Pdict['transform'][isubj].tocsr()
            else:
                Psparse=Pdict['transform']
            
            chacoconn_parc=Psparse.T.tocsr() @ chacoconn @ Psparse
            chacovol_parc=sparse.csr_matrix(chacoconn_parc.sum(axis=0)+chacoconn_parc.sum(axis=1).T)
            chacovol_parc.eliminate_zeros()
            
            chacofile_subj=tmpdir+'/chacovol_parc%05d_subj%05d.npz' % (iparc,isubj)
            sparse.save_npz(chacofile_subj,chacovol_parc,compressed=False)
            
            #sparse.save_npz(chacofile_subj,chacoconn.multiply(Aconnsum),compressed=False)
            chacofile_subj=tmpdir+'/chacoconn_parc%05d_subj%05d.npz' % (iparc,isubj)
            sparse.save_npz(chacofile_subj,chacoconn_parc,compressed=False)
            #chacovol_parc=((T_allsubj[isubj,:]>0) @ (B @ Psparse)).multiply(Asum[isubj,:] @ Psparse))
            
            if do_compute_denom:
                Aconnsum_parc=Psparse.T.tocsr() @ Aconnsum @ Psparse
                Aconnsum_parc.eliminate_zeros()
                chacofile_subj=tmpdir+'/chacoconn_parc%05d_denom_subj%05d.npz' % (iparc,isubj)
                sparse.save_npz(chacofile_subj,Aconnsum_parc,compressed=False)
###########################################################

print('Mapping to endpoints and ChaCo', end='',flush=True)

#HACK_NUMBER_OF_SUBJECTS=50
HACK_NUMBER_OF_SUBJECTS=numsubj

#Now multiply with B mat to go from tracks->endpoints
#result = (numsubj x numvoxels)
starttime_endpoints=time.time()

if do_pairwise:
    #print('Mapping to conn', end='',flush=True)

    #Now multiply with B mat to go from tracks->endpoints
    #result = (numsubj x numvoxels)
    starttime_endpoints=time.time()

    #multiproc_cores=1
    P=multiprocessing.Pool(multiproc_cores)
    #P.map(map_to_endpoints, range(numsubj))
    P.map(map_to_endpoints_conn, range(HACK_NUMBER_OF_SUBJECTS))

    P.close()

    print(' took %s on %d threads' % (durationToString(time.time()-starttime_endpoints),multiproc_cores))

else:    
    starttime_endpoints=time.time()

    #multiproc_cores=1
    P=multiprocessing.Pool(multiproc_cores)
    #P.map(map_to_endpoints_numerator, range(numsubj))
    P.map(map_to_endpoints_numerator, range(HACK_NUMBER_OF_SUBJECTS))

    P.close()

    #endpointmat=None

    print(' took %s on %d threads' % (durationToString(time.time()-starttime_endpoints),multiproc_cores))

########


endpointmat=None
trackweights=None
tracklengths=None

if do_debug:
    print(tmpdir)

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

if do_save_fullvol:
    chaco_output_list.append({"name":"chacovol_%s" % (origres_name), "numerator":'chacovol_subj%05d.npz', "denominator":'Asum', 
        "parcelindex":None, "reshape": refimg, "voxmm": voxmm})

if do_save_fullconn and do_pairwise:
    #chaco_output_list.append({"name":"chacoconn_%s" % (origres_name), "numerator":'chacoconn_subj%05d.npz', "denominator":'Aconnsum', 'parcelindex':None, 'reshape': None})
    chaco_output_list.append({"name":"chacoconn_%s" % (origres_name), 
        "numerator":'chacoconn_subj%05d.npz', 
        "denominator": 'chacoconn_denom_subj%05d.npz', 
        "parcelindex":None, "reshape": None})

if Psparse_list:
    for iparc in range(len(Psparse_list)):
        chaco_output_list.append({"name":"chacovol_%s" % (Psparse_list[iparc]['name']), 
            "numerator": 'chacovol_parc%05d_subj%%05d.npz' % (iparc), 
            "denominator":'Asum',
            "parcelindex":iparc, 
            "reshape": Psparse_list[iparc]['reshape'], 
            "voxmm": Psparse_list[iparc]['voxmm']})
        if do_pairwise:
            chaco_output_list.append({"name":"chacoconn_%s" % (Psparse_list[iparc]['name']), 
                "numerator": 'chacoconn_parc%05d_subj%%05d.npz' % (iparc), 
                "denominator":'chacoconn_parc%05d_denom_subj%%05d.npz' % (iparc),
                "parcelindex":iparc, "reshape": None})


#chaco_output_list=[chaco_output_list[0]]



def save_chaco_output(chaco_output):   
#for chaco_output in chaco_output_list:
    #print(chaco_output)
    chaco_allsubj=[]
    chaco_denom_allsubj=[]
    
    Psparse=None
    output_reshape=chaco_output['reshape']
    if chaco_output['parcelindex'] is not None:
        Psparse=Psparse_list[chaco_output['parcelindex']]['transform']
            
    starttime_accum=time.time()
    #for isubj in range(numsubj):
    for isubj in range(HACK_NUMBER_OF_SUBJECTS):
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
            chaco_denom = chaco_denom.multiply(chaco_numer>0)
            chaco_denom.eliminate_zeros()
        
        elif chaco_output['denominator'] == 'Aconnsum':
            if Ptmp is None:
                chaco_denom=Aconnsum[isubj]
            else:
                chaco_denom=Ptmp.T.tocsr() @ Aconnsum[isubj] @ Ptmp
            chaco_denom = chaco_denom.multiply(chaco_numer>0)
            chaco_denom.eliminate_zeros()
        
        else:
            chacofile_subj_denom=tmpdir+'/'+chaco_output['denominator'] % (isubj)
            chaco_denom=sparse.load_npz(chacofile_subj_denom)
        
        chaco_denom_allsubj.append(chaco_denom.copy())
        
        chaco_denom.data=1/chaco_denom.data.astype(np.float32)
        chaco_allsubj.append(chaco_numer.multiply(chaco_denom))
        
        os.remove(chacofile_subj)
        if chacofile_subj_denom is not None:
            os.remove(chacofile_subj_denom)
            
    if do_debug:
        print('Loading in %s took %s' % (chaco_output['name'],durationToString(time.time()-starttime_accum)))

    #compute mean and stdev of chaco scores across all reference subjects
    if chaco_allsubj[0].shape[0] == 1:
        #stackable
        chaco_allsubj=sparse.vstack(chaco_allsubj)
        chaco_denom_allsubj=sparse.vstack(chaco_denom_allsubj)
        chacomean=np.array(np.mean(chaco_allsubj,axis=0))
        chacostd=np.sqrt(np.array(np.mean(chaco_allsubj.multiply(chaco_allsubj),axis=0) - chacomean**2))
    else:
        chacomean=0
        chacosqmean=0
        for ch in chaco_allsubj:
            chacomean+=ch
            chacosqmean+=ch.multiply(ch)
        chacomean/=len(chaco_allsubj)
        chacosqmean/=len(chaco_allsubj)
        chacostd=np.sqrt(chacosqmean - chacomean.multiply(chacomean))

    outfile_pickle=outputbase+'_'+chaco_output['name']+"_allref.pkl"
    pickle.dump(chaco_allsubj, open(outfile_pickle,"wb"))

    outfile_pickle=outputbase+'_'+chaco_output['name']+"_allref_denom.pkl"
    pickle.dump(chaco_denom_allsubj,open(outfile_pickle,"wb"))
    
    if output_reshape is None:
            
        #sparse.save_npz(tmpdir+'/'+chaco_output['name']+'_mean.npz',chacomean,compressed=False)
        #sparse.save_npz(tmpdir+'/'+chaco_output['name']+'_stdev.npz',chacostd,compressed=False)
        #print(chacomean)
        #print(chacostd)
        pickle.dump(chacomean, open(outputbase+'_'+chaco_output['name']+'_mean.pkl', "wb"))
        pickle.dump(chacostd, open(outputbase+'_'+chaco_output['name']+'_stdev.pkl', "wb"))
    
    else:
        outimg=nib.Nifti1Image(np.reshape(np.array(chacomean),output_reshape.shape),affine=output_reshape.affine, header=output_reshape.header)
        imgfile=outputbase+'_glassbrain_%s_mean.png' % (chaco_output['name'])
        plotting.plot_glass_brain(outimg,output_file=imgfile,colorbar=True)
        nib.save(outimg,outputbase+'_%s_mean.nii.gz' % (chaco_output['name']))
        
        outimg=nib.Nifti1Image(np.reshape(np.array(chacostd),output_reshape.shape),affine=output_reshape.affine, header=output_reshape.header)
        imgfile=outputbase+'_glassbrain_%s_stdev.png' % (chaco_output['name'])
        plotting.plot_glass_brain(outimg,output_file=imgfile,colorbar=True)
        nib.save(outimg,outputbase+'_%s_stdev.nii.gz' % (chaco_output['name']))
        
    if do_debug:
        print('Saving %s took %s' % (chaco_output['name'],durationToString(time.time()-starttime_accum)))
    
#only use 2 cores since each chacoconn uses so much memory
P=multiprocessing.Pool(3)
#P.map(map_to_endpoints, range(numsubj))
P.map(save_chaco_output,chaco_output_list)

P.close()

imglesion_mni=nib.Nifti1Image(Ldata>0,affine=refimg.affine, header=refimg.header)
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
        
        smoothvol=lambda x: ndimage.gaussian_filter(np.reshape(np.array(x.todense()),chaco_output['reshape'].shape),sigma=smoothing_fwhm/2.35482/chaco_output['voxmm'])

        #note: the non-sparse version of this runs in ~20 seconds on 16 core, but takes up 28MB*420=12GB temporarily
        
        if smoothing_mode == "ratio":
            def smoothfun(rowindex):
                outsmooth=sparse.csr_matrix(smoothvol(chaco_allsubj[rowindex,:]).flatten())
                outsmooth.eliminate_zeros()
                return outsmooth
        
        elif smoothing_mode == "counts":
            def smoothfun(rowindex):
                outsmooth_numer=sparse.csr_matrix(smoothvol(chaco_allsubj[rowindex,:]).flatten())
                outsmooth_denom=sparse.csr_matrix(smoothvol(chaco_denom_allsubj[rowindex,:]).flatten())
                outsmooth_numer.eliminate_zeros()
                outsmooth_denom.eliminate_zeros()
    
                outsmooth_denom = outsmooth_denom.multiply(outsmooth_numer>0)
                outsmooth_denom.eliminate_zeros()
    
                outsmooth_denom.data=1/outsmooth_denom.data
                outsmooth_numer=outsmooth_numer.multiply(outsmooth_denom)
                return outsmooth_numer
        
        P=multiprocessing.Pool(multiproc_cores)
        chaco_smooth=P.map(smoothfun, range(chaco_allsubj.shape[0]))
        P.close()
        
        chaco_smooth=sparse.vstack(chaco_smooth)
        chaco_smooth_mean=np.array(np.mean(chaco_smooth,axis=0))
        chaco_smooth_std=np.sqrt(np.array(np.mean(chaco_smooth.multiply(chaco_smooth),axis=0) - chaco_smooth_mean**2))

        outimg=nib.Nifti1Image(np.reshape(np.array(chaco_smooth_mean),chaco_output['reshape'].shape),affine=chaco_output['reshape'].affine, header=chaco_output['reshape'].header)
        imgfile=outputbase+'_glassbrain_%s_smooth%gmm_mean.png' % (chaco_output['name'],smoothing_fwhm)
        plotting.plot_glass_brain(outimg,output_file=imgfile,colorbar=True)
        nib.save(outimg,outputbase+'_%s_smooth%gmm_mean.nii.gz' % (chaco_output['name'],smoothing_fwhm))
        
        outimg=nib.Nifti1Image(np.reshape(np.array(chaco_smooth_std),chaco_output['reshape'].shape),affine=chaco_output['reshape'].affine, header=chaco_output['reshape'].header)
        imgfile=outputbase+'_glassbrain_%s_smooth%gmm_stdev.png' % (chaco_output['name'],smoothing_fwhm)
        plotting.plot_glass_brain(outimg,output_file=imgfile,colorbar=True)
        nib.save(outimg,outputbase+'_%s_smooth%gmm_stdev.nii.gz' % (chaco_output['name'],smoothing_fwhm))
        
print('NeMo took a total of %s for %s' % (durationToString(time.time()-starttime),lesionfile))

###################################################################################################################
###################################################################################################################
exit(0)

if do_smooth:
    print('Smoothing individual ChaCo volumes at FWHM=%.2fmm (Just to generate a pretty mean image)' % (smoothing_fwhm))
    smooth_infile_list=[tmpdir+'/chacovol_subj%05d.npz' % (isubj) for isubj in range(numsubj)]
    smooth_outfile_list=[tmpdir+'/chacovol_subj%05d_smoothed.npz' % (isubj) for isubj in range(numsubj)]
    smoothstart=time.time()
    P=multiprocessing.Pool(multiproc_cores)
    chaco_smooth=P.map(smoothfun, zip(smooth_infile_list,smooth_outfile_list))
    P.close()
    
    #this one works!
    #chaco_smooth=sum(chaco_smooth)/numsubj
    
    #need to play around to see how to correctly get the std over this sparse list
    chaco_smooth=sparse.vstack(chaco_smooth)
    chaco_smooth_mean=np.array(chaco_smooth.mean(axis=0))
    chaco_smooth_std=np.sqrt(np.array(chaco_smooth.multiply(chaco_smooth).mean(axis=0) - chaco_smooth_mean**2))
    chaco_smooth=None
    
    #chaco_smooth=None
    #for f in smooth_outfile_list:
    #    if chaco_smooth is None:
    #        #chaco_smooth=np.load(f)
    #        chaco_smooth=sparse.load_npz(f)
    #    else:
    #        #chaco_smooth+=np.load(f)
    #        chaco_smooth+=sparse.load_npz(f)
    #    os.remove(f)
    #chaco_smooth/=numsubj

    
    print('Smoothing took %s' % (durationToString(time.time()-smoothstart)))

    #imgsmooth=nib.Nifti1Image(chaco_smooth,affine=refimg.affine, header=refimg.header)
    
    #before doing the stdev change:
    #imgsmooth=nib.Nifti1Image(np.reshape(np.array(chaco_smooth.todense()),volshape),affine=refimg.affine, header=refimg.header)
     
    imgsmooth=nib.Nifti1Image(np.reshape(chaco_smooth_mean,volshape),affine=refimg.affine, header=refimg.header)
    imgfile_smooth=outputbase+'_glassbrain_chaco_smooth%gmm_mean.png' % (smoothing_fwhm)
    plotting.plot_glass_brain(imgsmooth,output_file=imgfile_smooth,colorbar=True)
    nib.save(imgsmooth,outputbase+'_chaco_smooth%gmm_mean.nii.gz' % (smoothing_fwhm))
    
    ##########
    imgsmooth_std=nib.Nifti1Image(np.reshape(chaco_smooth_std,volshape),affine=refimg.affine, header=refimg.header)
    imgfile_smooth_std=outputbase+'_glassbrain_chaco_smooth%gmm_stdev.png' % (smoothing_fwhm)
    plotting.plot_glass_brain(imgsmooth_std,output_file=imgfile_smooth_std,colorbar=True)
    nib.save(imgsmooth_std,outputbase+'_chaco_smooth%gmm_stdev.nii.gz' % (smoothing_fwhm))
    
chaco_allsubj=[]
starttime_merge_final=time.time()
for isubj in range(numsubj):
    chacofile_subj=tmpdir+'/chacovol_subj%05d.npz' % (isubj)
    chaco_allsubj.append(sparse.load_npz(chacofile_subj))
    os.remove(chacofile_subj)
os.rmdir(tmpdir)
print('Loading final chaco maps took %s' % (durationToString(time.time()-starttime_merge_final)))


chaco_allsubj=sparse.vstack(chaco_allsubj)
sparse.save_npz(outputbase+'_chaco_allref.npz',chaco_allsubj,compressed=False)

chacomean=np.array(np.mean(chaco_allsubj,axis=0))
imgchaco=nib.Nifti1Image(np.reshape(chacomean,volshape),affine=refimg.affine, header=refimg.header)
imgfile_mean=outputbase+'_glassbrain_chaco_mean.png'
plotting.plot_glass_brain(imgchaco,output_file=imgfile_mean,colorbar=True)
nib.save(imgchaco,outputbase+'_chaco_mean.nii.gz')

###########

chacostd=np.sqrt(np.array(np.mean(chaco_allsubj.multiply(chaco_allsubj),axis=0) - chacomean**2))
imgchaco_std=nib.Nifti1Image(np.reshape(chacostd,volshape),affine=refimg.affine, header=refimg.header)
imgfile_std=outputbase+'_glassbrain_chaco_stdev.png'
plotting.plot_glass_brain(imgchaco_std,output_file=imgfile_std,colorbar=True)
nib.save(imgchaco_std,outputbase+'_chaco_stdev.nii.gz')
###########

imglesion_mni=nib.Nifti1Image(Ldata>0,affine=refimg.affine, header=refimg.header)
imgfile_lesion=outputbase+'_glassbrain_lesion_orig.png'
plotting.plot_glass_brain(imglesion_mni,output_file=imgfile_lesion,cmap='jet',colorbar=True)

print('NeMo took a total of %s for %s' % (durationToString(time.time()-starttime),lesionfile))


