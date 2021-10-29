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
    parser.add_argument('--parcellation','-p',dest='parcellation',help='Parcellation to fill', required=True)


    
    args=parser.parse_args(argv)
    
    if args.parcellation is None:
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
    else:
        print("Input data dimensions do not match parcellation")
        exit(1)
    
    newvol=np.zeros(parcvol.shape)
    newvol[parcmask]=np.mean(parcdata[uparc_idx],axis=1)
    
    return newvol

def save_parc_to_volume(inputfile, outputfile, parcellation_file):
    imgdata=load_input(inputfile)
    imgdata[np.isnan(imgdata)]=0
    
    refimg=nib.load(parcellation_file)
    parcvol=refimg.get_fdata()
    imgdata=parcellation_to_volume(imgdata,parcvol)

    refhdr=refimg.header.copy()
    refhdr.set_data_dtype(imgdata.dtype)
    imgnew=nib.Nifti1Image(imgdata,affine=refimg.affine, header=refhdr)
    nib.save(imgnew,outputfile)

if __name__ == "__main__":
    args=argument_parse(sys.argv[1:])
    imgshape=save_parc_to_volume(inputfile=args.infile, outputfile=args.outfile, parcellation_file=args.parcellation)
