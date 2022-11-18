import nibabel as nib
from scipy import sparse
import sys
import argparse 
import numpy as np
import pickle

def argument_parse(argv):
    parser=argparse.ArgumentParser(description='Convert a parcellated chacovol output to NIFTI')
    
    parser.add_argument('--in','-i',action='store',dest='infile',help='input chacovol file (.txt, .pkl, etc.)', required=True)
    parser.add_argument('--out','-o',action='store', dest='outfile', help='output NIFTI file', required=True)
    parser.add_argument('--parcellation','-p',dest='parcellation',help='Parcellation to fill', required=False)
    parser.add_argument('--ciftitemplate','-c',dest='cifti_template',help='Cifti template', required=False)
    
    args=parser.parse_args(argv)
    
    if args.parcellation is None and args.cifti_template is None:
        if not all([x.lower().endswith(".nii") or x.lower().endswith(".nii.gz") for x in args.volumefile]):
            print("Inputs must all be NIfTI volumes unless a parcellation is provided")
            exit(1)
    
    return args

def load_input(inputfile):
    if inputfile.lower().endswith(".txt"):
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
    elif parcdata.shape[0] >= max(uparc):
        #this happens if input is cifti91k (full 0-91282) and parcvol does not have all of those indices
        parcdata=parcdata[uparc.astype(np.uint32)-1,:]
    elif parcdata.shape[1] >= max(uparc):
        #this happens if input is cifti91k (full 0-91282) and parcvol does not have all of those indices
        parcdata=parcdata[:,uparc.astype(np.uint32)-1].T
    else:
        print("Input data dimensions do not match parcellation")
        exit(1)
    
    newvol=np.zeros(parcvol.shape)
    newvol[parcmask]=np.mean(parcdata[uparc_idx],axis=1)
    
    return newvol

def save_parc_to_volume(inputfile, outputfile, parcellation_file=None, cifti_template_file=None):
    imgdata=load_input(inputfile)
    imgdata[np.isnan(imgdata)]=0
    
    if parcellation_file is not None:
        refimg=nib.load(parcellation_file)
        if not isinstance(refimg,nib.Nifti1Image):
            print("Unknown file format for parcellation input: ",type(refimg))
            exit(1)
        parcvol=refimg.get_fdata()
        imgdata=parcellation_to_volume(imgdata,parcvol)
        refhdr=refimg.header.copy()
        refhdr.set_data_dtype(imgdata.dtype)
        imgnew=nib.Nifti1Image(imgdata,affine=refimg.affine, header=refhdr)
        
    elif cifti_template_file is not None:
        refimg=nib.load(cifti_template_file)
        if not isinstance(refimg,nib.cifti2.cifti2.Cifti2Image):
            print("Unknown file format for cifti template: ",type(refimg))
            exit(1)
        imgdata=imgdata.reshape(refimg.shape).astype(refimg.get_data_dtype())
        imgnew=nib.cifti2.cifti2.Cifti2Image(imgdata,header=refimg.header)
        
    else:
        print("Must provide either parcellation or cifti template")
        exit(1)
    
    nib.save(imgnew,outputfile)

if __name__ == "__main__":
    args=argument_parse(sys.argv[1:])
    imgshape=save_parc_to_volume(inputfile=args.infile, outputfile=args.outfile, parcellation_file=args.parcellation, cifti_template_file=args.cifti_template)
