import numpy as np
import nibabel as nib
from scipy.ndimage.morphology import distance_transform_edt
import sys
import argparse


def argument_parser(argv):
    parser=argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter,
        description='Dilate parcellation by specific number of voxels (or mm). \nNOTE: Result is different from serial dilation. To match serial X serial dilation iterations, use -dilatevox <1.4*X>')
    parser.add_argument('-dilatevox',action='store',dest='dilatevox',type=float,help='Number of voxels to erode by')
    parser.add_argument('-dilatemm',action='store',dest='dilatemm',type=float,help='mm to erode by')
    parser.add_argument('-distvol',action='store',dest='distvol',help='save dilation distances to this file (optional)')
    parser.add_argument('invol',action='store')
    parser.add_argument('outvol',action='store')

    return parser.parse_args(argv)
    

def parselist(liststring):
    outlist=[]
    for p in liststring.split(","):
        if not p:
            continue
        if "-" in p:
            pp=p.split("-")
            outlist+=np.arange(float(pp[0]),float(pp[-1])+1).tolist()
        else:
            outlist+=[float(p)]
    return outlist

def main(argv):
    args=argument_parser(argv)
    involfile=args.invol
    outvolfile=args.outvol
    dilatevox=args.dilatevox
    dilatemm=args.dilatemm
    distvolfile=args.distvol

    
    Pimg=nib.load(involfile)
    voxmm=np.sqrt(Pimg.affine[:3,0].dot(Pimg.affine[:3,0]))
    P=Pimg.get_fdata()

    if dilatevox is not None:
        distvox=dilatevox
    elif dilatemm is not None:
        distvox=dilatemm/voxmm
    else:
        print("Must provide either -dilatevox or -dilatemm")
        exit(1)
        
    print("Input volume voxel size is %.3fmm" % (voxmm))
    print("Dilating by %.3f voxels" % (distvox))
    
    Pdist,Pidx=distance_transform_edt(P==0,return_indices=True)
    Pnn=P[Pidx[0],Pidx[1],Pidx[2]]
    if not np.isinf(distvox):
        #given the floating point precision, Pdist=0.999999 or 1.000001 sometimes
        #so pad the distvox just to make sure we catch those
        distvox+=0.01
        Pnn=Pnn*(Pdist<=distvox)
    
    if distvolfile is not None:
        Pnew=nib.Nifti1Image(Pdist.astype(np.float64),affine=Pimg.affine, header=Pimg.header)
        nib.save(Pnew,distvolfile)

    Pnew=nib.Nifti1Image(Pnn.astype(Pimg.get_data_dtype()),affine=Pimg.affine, header=Pimg.header)

    nib.save(Pnew,outvolfile)

if __name__ == "__main__":
    main(sys.argv[1:])