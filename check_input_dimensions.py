import nibabel as nib
import sys
import argparse 
import numpy as np

def argument_parse(argv):
    parser=argparse.ArgumentParser(description='Print dimensions for input volume or multiple input volumes')
    
    parser.add_argument('volumefile',nargs='*',action='store',help='one or more input volumes (eg: .nii files)')
    
    args=parser.parse_args(argv)
    
    if not args.volumefile:
        print("Must provide at least one input volume!")
        parser.print_help()
        exit(0)
    
    return args

def check_input_list_dimensions(inputlist):
    imgshape=None
    
    for i in inputlist:
        img=nib.load(i)
        if imgshape is None:
            imgshape=img.shape
        else:
            if imgshape != img.shape:
                return None
    
    return imgshape

if __name__ == "__main__":
    args=argument_parse(sys.argv[1:])
    imgshape=check_input_list_dimensions(args.volumefile)
    if imgshape is None:
        #mismatched input sizes
        sys.exit(1)
    else:
    	#print("%sx%sx%s" % imgshape)
        print("x".join([str(x) for x in imgshape]))