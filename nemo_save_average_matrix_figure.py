import sys
import argparse 
import numpy as np
import pickle
from matplotlib import pyplot as plt
from scipy import sparse

def argument_parse_savematrixfig(argv):
    parser=argparse.ArgumentParser(description='Save a matrix image for an input chacoconn or average or multiple input chacoconns')
    
    parser.add_argument('--out','-o',action='store', dest='outfile', required=True,help='output image file (eg: chacoconn.png)')
    parser.add_argument('--cmap','--colormap','-c',action='store', dest='colormap',help='matplotlib colormap name (eg: jet,hot,...). Default: hot')
    parser.add_argument('--title','-t',action='store',dest='title',help='title to draw on top of figure')
    parser.add_argument('--sym','-s',action='store_true',dest='sym',help='Make triangular matrix symmetric')
    parser.add_argument('--maxsize',action='store',dest='maxsize',type=float,default=1000,help='Maximum matrix dimension to display. Default: 1000')
    parser.add_argument('connfile',nargs='*',action='store',help='one or more input connfiles (eg: chacoconn.pkl files)')
    
    args=parser.parse_args(argv)
    
    if not args.connfile:
        print("Must provide at least one input connfile!",file=sys.stderr)
        parser.print_help()
        exit(0)
    
    return args

def make_triangular_matrix_symmetric(m):
    has_triu=np.any(np.triu(m!=0,1))
    has_tril=np.any(np.tril(m!=0,-1))
    if has_triu and not has_tril:
        m+=np.triu(m,1).T
    elif has_tril and not has_triu:
        m+=np.tril(m,-1).T
    return m

def load_input(inputfile,sym=False):
    if inputfile.lower().endswith(".txt"):
        imgdata=np.loadtxt(inputfile)
    elif inputfile.lower().endswith(".pkl"):
        imgdata=pickle.load(open(inputfile,"rb"))
    if sparse.issparse(imgdata):
        imgdata=imgdata.toarray()
    if len(imgdata.shape)==2 and imgdata.shape[0]==imgdata.shape[1]:
        imgdata=make_triangular_matrix_symmetric(imgdata)
    return imgdata

def average_input_matrices(inputlist,sym=False,maxsize=None):
    avgdata=None
    imgshape=None
    
    for i in inputlist:
        imgdata=load_input(i,sym)
        imgdata[np.isnan(imgdata)]=0
        if avgdata is None:
            avgdata=imgdata
            imgshape=imgdata.shape
        else:
            if imgshape != imgdata.shape:
                return None
            avgdata+=imgdata
        if maxsize is None or np.isinf(maxsize):
            continue
        if max(imgshape) > maxsize:
            print("Matrix exceeds maximum size. %d > %d" % (max(imgshape),maxsize),file=sys.stderr)
            exit(0)
    
    avgdata/=len(inputlist)
    
    return avgdata, imgshape

def save_matrix_fig(outputfile, inputlist, colormap=None,title=None,sym=False,maxsize=None):
    avgdata,imgshape = average_input_matrices(inputlist,sym=sym,maxsize=maxsize)
    
    if colormap is None:
        colormap="hot"
    fig=plt.figure()
    ax=plt.imshow(avgdata,cmap=colormap)
    plt.xlabel('ROI')
    plt.ylabel('ROI')
    fig.colorbar(ax)
    if title is not None:
        plt.title(title)
    fig.savefig(outputfile)
    plt.close()
    
    return imgshape

if __name__ == "__main__":
    args=argument_parse_savematrixfig(sys.argv[1:])
    imgshape=save_matrix_fig(outputfile=args.outfile,inputlist=args.connfile,colormap=args.colormap,title=args.title,sym=args.sym,maxsize=args.maxsize)
    if imgshape is None:
        #mismatched input sizes
        sys.exit(1)
    else:
    	#print("%sx%sx%s" % imgshape)
        print("x".join([str(x) for x in imgshape]))