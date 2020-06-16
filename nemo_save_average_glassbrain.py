import nibabel as nib
from nilearn import plotting, image
import sys
import argparse 
import numpy as np

parser=argparse.ArgumentParser(description='Save a glassbrain image for an input volume or average or multiple input volumes')

parser.add_argument('--out','-o',action='store', dest='outfile', required=True,help='output image file (eg: glassbrain.png)')
parser.add_argument('--cmap','--colormap','-c',action='store', dest='colormap',help='matplotlib colormap name (eg: jet,hot,...)')
parser.add_argument('volumefile',nargs='*',action='store',help='one or more input volumes (eg: .nii files)')
parser.add_argument('--binarize','-b',action='store_true',help='Binarize each input volume (!=0)')

args=parser.parse_args()

outfile=args.outfile
colormap=args.colormap
imglist=args.volumefile
binarize=args.binarize
if not imglist:
    print("Must provide at least one input volume!")
    parser.print_help()
    exit(0)

avgdata=None
imgshape=None
for i in imglist:
    img=nib.load(i)
    imgdata=img.get_fdata()
    if binarize:
        imgdata=(imgdata!=0).astype(np.float32)
    if avgdata is None:
        avgdata=imgdata
        imgshape=imgdata.shape
    else:
        if imgshape != imgdata.shape:
            sys.exit(1)
        avgdata+=imgdata

avgdata/=len(imglist)

imgavg=nib.Nifti1Image(avgdata,affine=img.affine, header=img.header)
plotting.plot_glass_brain(imgavg,output_file=outfile,cmap=colormap,colorbar=True)

print("%sx%sx%s" % imgshape)
