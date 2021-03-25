import nibabel as nib
from nilearn import plotting
from scipy import sparse
import sys
import argparse 
import numpy as np
import pickle

def argument_parse(argv):
    parser=argparse.ArgumentParser(description='Save a glassbrain image for an input volume or average or multiple input volumes')
    
    parser.add_argument('--out','-o',action='store', dest='outfile', required=True,help='output image file (eg: glassbrain.png)')
    parser.add_argument('--cmap','--colormap','-c',action='store', dest='colormap',help='matplotlib colormap name (eg: jet,hot,...). Default: cold_white_hot')
    parser.add_argument('volumefile',nargs='*',action='store',help='one or more input volumes (eg: .nii files)')
    parser.add_argument('--binarize','-b',action='store_true',help='Binarize each input volume (!=0)')
    parser.add_argument('--parcellation','-p',dest='parcellation',help='Parcellation to fill')
    
    args=parser.parse_args(argv)
    
    if not args.volumefile:
        print("Must provide at least one input volume!")
        parser.print_help()
        exit(0)
    
    if args.parcellation is None:
        if not all([x.lower().endswith(".nii") or x.lower().endswith(".nii.gz") for x in args.volumefile]):
            print("Inputs must all be NIfTI volumes unless a parcellation is provided")
            exit(1)
    
    return args

def load_input(inputfile):
    if inputfile.lower().endswith(".nii") or inputfile.lower().endswith(".nii.gz"):
        img=nib.load(inputfile)
        imgdata=img.get_fdata()
    elif inputfile.lower().endswith(".txt"):
        imgdata=np.loadtxt(inputfile)
    elif inputfile.lower().endswith(".pkl"):
        imgdata=pickle.load(open(inputfile,"rb"))
    if sparse.issparse(imgdata):
        imgdata=imgdata.toarray()
    return imgdata
        
def parcellation_to_volume(parcdata, parcvol):
    parcmask=parcvol!=0
    uparc,uparc_idx=np.unique(parcvol[parcmask],return_inverse=True)
    
    if parcdata.shape[0] == len(uparc):
        pass
    elif parcdata.shape[1] == len(uparc):
        parcdata=parcdata.T
    else:
        print("Input data dimensions do not match parcellation")
        exit(1)
    
    newvol=np.zeros(parcvol.shape)
    newvol[parcmask]=np.mean(parcdata[uparc_idx],axis=1)
    
    return newvol

def save_glassbrain(outputfile, inputlist, binarize=False, colormap="cold_white_hot", parcellation_file=None):
    avgdata=None
    imgshape=None

    for i in inputlist:
        imgdata=load_input(i)
        imgdata[np.isnan(imgdata)]=0
        if binarize:
            imgdata=(imgdata!=0).astype(np.float32)
        if avgdata is None:
            avgdata=imgdata
            imgshape=imgdata.shape
        else:
            if imgshape != imgdata.shape:
                return None
            avgdata+=imgdata
    
    avgdata/=len(inputlist)
    
    if parcellation_file is None:
        refimg=nib.load(inputlist[0])
    else:
        refimg=nib.load(parcellation_file)
        parcvol=refimg.get_fdata()
        avgdata=parcellation_to_volume(avgdata,parcvol)
    
    
    imgavg=nib.Nifti1Image(avgdata,affine=refimg.affine, header=refimg.header)
    plotting.plot_glass_brain(imgavg,output_file=outputfile,cmap=colormap,colorbar=True)
    
    return imgshape

if __name__ == "__main__":
    args=argument_parse(sys.argv[1:])
    imgshape=save_glassbrain(args.outfile,args.volumefile,args.binarize,args.colormap,args.parcellation)
    if imgshape is None:
        #mismatched input sizes
        sys.exit(1)
    else:
    	#print("%sx%sx%s" % imgshape)
        print("x".join([str(x) for x in imgshape]))