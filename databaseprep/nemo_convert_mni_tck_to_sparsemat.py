import nibabel as nib
import numpy as np
import time
from scipy.sparse import csc_matrix
from scipy.io import loadmat, savemat
import sys


#########################
def convert_tracks_to_sparse(tckfile,weightfile,lengthfile,niifile,outfile):
    starttime=time.time()
    img = nib.load(niifile)

    volxfm=img.affine
    volsize=img.shape

    Txyz2vox=np.float32(np.linalg.inv(volxfm))

    starttime=time.time()
    weights=np.loadtxt(weightfile);
    tracklengths=np.loadtxt(lengthfile);           
    starttime=time.time()


    tckfid=open(tckfile,'rb')


    c=0

    header={}

    fileval=[]

    while True:
        line=tckfid.readline()
        c+=1
        if not line:
            break
        linestr=line.decode('utf-8').strip()
        if c == 1:
            if not linestr == 'mrtrix tracks':
                raise Error('Not track file!')
                break
            else:
                continue


        if linestr == 'END':
            break
        keyval=linestr.split(':')

        if len(keyval) < 2:
            raise Error('no keyvals')
            break

        if keyval[0] == 'file':
            fileval=keyval[1]
            continue

        header[keyval[0].strip()]=keyval[1].strip()
    tckfid.close()

    print(header)

    try:
        fileoffset=int(fileval.split('.')[1])
    except:
        raise Error('Error parsing file offset')

    datatype=header['datatype'].lower()
    byteorder=datatype[-2:]

    if not datatype.startswith('float32'):
        raise Error('.tck file only supports float32, but found %s instead' % (datatype))

    if byteorder=='le':
        opentype='<f4'
        datatype=datatype[:-2]
    elif byteorder=='be':
        opentype='>f4'
        datatype=datatype[:-2]
    else:
        print('Unknown datatype')

    #if strcmp(byteorder, 'le')
    #  f = fopen (filename, 'r', 'l');
    #  datatype = datatype(1:end-2);
    #elseif strcmp(byteorder, 'be')
    #  f = fopen (filename, 'r', 'b');
    #  datatype = datatype(1:end-2);
    #else
    #  error('unexpected data type - aborting');
    #end


    data=np.fromfile(file=tckfile,dtype=opentype,offset=fileoffset)

    print('Reading took %.3f seconds' % (time.time()-starttime))
    print('Total values read: %d' % (data.size))
    N = int(data.size/3);
    data = np.reshape(data, [N,3]);
    #track data should end with row of [inf,inf,inf]
    if np.isinf(data[-1,0]):
        data=data[:-1,:]

    print('Total coordinate size including nans: (%d,%d)' % (data.shape))

    #dsteps=np.sqrt(np.sum(np.diff(data,axis=0)**2,axis=1))
    #dnan=np.isnan(data[:,0])
    #dnanidx=np.where(dnan)[0]
    #trackstart=np.insert(dnanidx[:-1]+1,0,0)
    #trackstop_sub1=dnanidx-1
    #tracklengths=np.zeros(len(trackstart))
    #for i in range(len(trackstart)):
    #    tracklengths[i]=np.sum(dsteps[trackstart[i]:trackstop_sub1[i]])                
    #print('Track lengths took %.3f seconds' % (time.time()-starttime))

    #print(data[-10:,:])
    #transform took 13 seconds
    data=np.round(data @ Txyz2vox[:3,:3] + Txyz2vox[:3,3])
    #print('Transforming took %.3f seconds' % (time.time()-starttime))
    #bounding took 10 seconds
    data=np.maximum(np.minimum(data,np.array(volsize,dtype=np.float32)-1),0)
    print('Transform and bound took %.3f seconds' % (time.time()-starttime))

    #dataxyz=data.copy()
    #convert voxel coords to voxel index (like sub2ind)
    #but this matches the ravel_multi_index output
    data=data[:,2] + data[:,1]*volsize[0] + data[:,0]*volsize[0]*volsize[1]
    print('Initial coords in voxindex: %d' % (data.size))
    #remove sequential duplicates
    data=data[np.append(data[:-1]!=data[1:],True)]
    print('After removing sequential duplicates: %d' % (data.size))
    dnan=np.isnan(data)
    dnanidx=np.where(dnan)[0]
    print('Reading took %.3f seconds' % (time.time()-starttime))

    #print(data[-10:])

    #sparse saved in matlab and loaded in is a csc_matrix:
    #csc_matrix((data,(row,col)),shape=(m,n))

    trackstart=np.insert(dnanidx[:-1]+1,0,0)
    trackstop=dnanidx
    tracklen=trackstop-trackstart
    #trackidx=np.zeros(data.shape)
    #for i in range(len(trackstart)):
    #    trackidx[trackstart[i]:trackstop[i]]=i
    print('Building trackidx took %.3f seconds' % (time.time()-starttime))

    trackstartvoxidx=data[trackstart][None,:].astype(int)
    trackstopvoxidx=data[trackstop-1][None,:].astype(int)

    numvoxels=np.prod(volsize)
    numtracks=len(trackstart)

    indptr=np.append(0,np.cumsum(tracklen))
    #A=csc_matrix((vals,(data[~dnan],trackidx[~dnan])),shape=(np.prod(volsize),len(trackstart)))
	#A=csr_matrix(((np.ones(np.sum(~dnan),dtype=bool),(data[~dnan],trackidx[~dnan])),shape=(np.prod(volsize),len(trackstart)))
    A=csc_matrix((np.ones(np.sum(~dnan),dtype=bool),data[~dnan],indptr),shape=(numvoxels,numtracks))

    print('Building sparsemat took %.3f seconds' % (time.time()-starttime))

    #clear memory from data
    data=None

    tidx=np.append(np.arange(numtracks),np.arange(numtracks))
    endpt=np.append(trackstartvoxidx,trackstopvoxidx)
    #B should be tracks x voxels
    B=csc_matrix((np.ones(tidx.shape,dtype=bool),(tidx,endpt)),shape=(numtracks,numvoxels))
	#B=csr_matrix((np.ones(tidx.shape,dtype=bool),(tidx,endpt)),shape=(numtracks,numvoxels))
    print('Building sparsemat B took %.3f seconds' % (time.time()-starttime))

    #these are needed frequently so we should precompute and store,
    #but store as sparse since most are non-brain
    Asum=csc_matrix(np.array(np.sum(A,axis=1)),dtype=np.int32)
    Asum_weighted=csc_matrix(A @ weights.T,dtype=np.float32)

    #save is 3.2GB with np.ones
    #save is 1.4GB with A>0
    #save is 770MB with A>0 and compression and 30 extra seconds to write (plus 13 sec to read in matlab, vs 4sec nocompress)

    #loading uncompressed 1.4GB into python = 1.2sec
    #loading compressed 770MB into python = 12 seconds
    savemat(outfile, \
        {'A':A,'B': B, 'Asum': Asum, 'Asum_weighted': Asum_weighted, \
        'track_lengths':tracklengths,'track_weights':weights, \
        'nifti_affine': img.affine, 'nifti_volshape': volsize, 'track_header': header} \
        ,do_compression=False)
    print('Saving sparsemat took %.3f seconds' % (time.time()-starttime))


fileroot=sys.argv[1]
niifile=sys.argv[2]
outfile=sys.argv[3]

#tckfile='/home/kwj2001/colossus_shared/HCP/mniwarptest/tmp_tckgen_100206/CSD_ifod2act5Mfsl_5M_MNI.tck'
#weightfile='/home/kwj2001/colossus_shared/HCP/mniwarptest/tmp_tckgen_100206/CSD_ifod2act5Mfsl_5M_sift2.txt'
#lengthfile='/home/kwj2001/colossus_shared/HCP/mniwarptest/tmp_tckgen_100206/CSD_ifod2act5Mfsl_5M_tracklength.txt'
#niifile='/usr/share/fsl/5.0/data/standard/MNI152_T1_1mm.nii.gz'
#outfile='/home/kwj2001/colossus_shared/HCP/testsparse_py_100206_ifod2act.mat'

tckfile=fileroot+'_MNI.tck'
weightfile=fileroot+'_sift2.txt'
lengthfile=fileroot+'_tracklength.txt'

convert_tracks_to_sparse(tckfile,weightfile,lengthfile,niifile,outfile)

