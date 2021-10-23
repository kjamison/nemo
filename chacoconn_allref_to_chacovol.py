import numpy as np
import sys
import argparse
import pickle
from scipy.io import savemat
from scipy import sparse
import nibabel as nib

def argument_parser(argv):
    parser=argparse.ArgumentParser(description='Convert NeMo pairwise allref to chacovol mean')
    parser.add_argument('-allref',action='store',dest='allrefpkl')
    parser.add_argument('-allrefdenom',action='store',dest='denompkl')
    parser.add_argument('-allrefnumer',action='store',dest='numerpkl')
    parser.add_argument('-refvol',action='store',dest='refvol') #for nifti output
    parser.add_argument('-output',action='store',dest='output')
    parser.add_argument('-keepdiag',action='store_true',dest='keepdiag')
    parser.add_argument('-subjidx',action='store',dest='subjidx',type=int) #for debugging
    parser.add_argument('-savenumer',action='store_true',dest='savenumer') #for debugging
    parser.add_argument('-savedenom',action='store_true',dest='savedenom') #for debugging
    parser.add_argument('-verbose',action='store_true',dest='verbose')
    
    return parser.parse_args(argv)

def main(argv):
    args=argument_parser(argv)
    ratiofile=args.allrefpkl
    denomfile=args.denompkl
    numerfile=args.numerpkl
    refvolfile=args.refvol
    output=args.output
    do_keepdiag=args.keepdiag
    verbose=args.verbose
    
    subjidx=args.subjidx
    do_savenumer=args.savenumer
    do_savedenom=args.savedenom
        
    if do_keepdiag:
        kdiag=0
    else:
        kdiag=1
    
    D=pickle.load(open(denomfile,"rb"))
    
    if not isinstance(D,list) or not sparse.issparse(D[0]):
        print("chacoconn allref_denom file is not a list of sparse matrices. Did you input chacovol allref by mistake?")
        exit(1)
    
    if numerfile:
        R=None
        N=pickle.load(open(numerfile,"rb"))
        if not isinstance(N,list) or not sparse.issparse(N[0]):
            print("chacoconn allref_numer file is not a list of sparse matrices. Did you input chacovol allref by mistake?")
            exit(1)
    else:
        R=pickle.load(open(ratiofile,"rb"))
        N=None
        if not isinstance(R,list) or not sparse.issparse(R[0]):
            print("chacoconn allref file is not a list of sparse matrices. Did you input chacovol allref by mistake?")
            exit(1)
    
    
    if subjidx is not None:
        #for debugging purposes, we might only want to see one subject's output at a time
        D=[D[subjidx]]
        if N is None:
            R=[R[subjidx]]
        else:
            N=[N[subjidx]]
    
    do_sparse_method=True
    
    if do_sparse_method:
        D=[sparse.triu(x,k=kdiag) for x in D]
        if N is None:
            R=[sparse.triu(x,k=kdiag) for x in R]
            N=[R[i].multiply(D[i]) for i in range(len(D))]
        else:
            N=[sparse.triu(x,k=kdiag) for x in N]
    
        Nsum=[x.sum(axis=0)+x.sum(axis=1).T-x.diagonal() for x in N]
        Dsum=[x.sum(axis=0)+x.sum(axis=1).T-x.diagonal() for x in D]
        if do_savenumer:
            chacovol=Nsum
        elif do_savedenom:
            chacovol=Dsum
        else:
            #normal use case
            chacovol=[Nsum[i].astype(np.float64)/Dsum[i].astype(np.float64) for i in range(len(Nsum))]
        chacovol=np.array(np.vstack(chacovol).T)
        chacovol[np.isnan(chacovol)]=0
    else:
        D=np.stack([x.toarray() for x in D],axis=2).astype(np.float64)
        if N is None:
            R=np.stack([x.toarray() for x in R],axis=2).astype(np.float64)
            N=D*R
        else:
            N=np.stack([x.toarray() for x in N],axis=2).astype(np.float64)
        
        for isubj in range(N.shape[2]):
            #make sure output is upper triangular and remove the diagonal if requested triu(k=1), otherwise triu(k=0)
            #then make each matrix symmetric by adding triu(k=1).T (ignores the diagonal either way)
            N[:,:,isubj]=np.triu(N[:,:,isubj],k=kdiag) + np.triu(N[:,:,isubj],k=1).T
            D[:,:,isubj]=np.triu(D[:,:,isubj],k=kdiag) + np.triu(D[:,:,isubj],k=1).T
    
        Nsum=np.sum(N,axis=0)
        Dsum=np.sum(D,axis=0)
    
        if do_savenumer:
            chacovol=Nsum
        elif do_savedenom:
            chacovol=Dsum
        else:
            #normal use case
            chacovol=Nsum/Dsum
        chacovol[np.isnan(chacovol)]=0
    
    chacovol_mean=np.atleast_2d(np.mean(chacovol,axis=-1))
    
    if verbose:
        print("chacovol_mean range: [%f,%f]" % (np.min(chacovol_mean),np.max(chacovol_mean)))
    
    if refvolfile is not None:
        Vref=nib.load(refvolfile)
    
    if output.lower().endswith(".mat"):
        savemat(output,{"chacovol": chacovol_mean},format='5',do_compression=True)
    elif output.lower().endswith(".pkl"):
        pickle.dump(chacovol_mean, open(output, "wb"))
    elif output.lower().endswith(".txt"):
        np.savetxt(output,chacovol_mean,fmt="%.10f")
    elif output.lower().endswith(".nii.gz") or output.lower().endswith(".nii"):
        Vnew=nib.Nifti1Image(np.reshape(chacovol_mean,Vref.shape),affine=Vref.affine,header=Vref.header)
        nib.save(Vnew,output)
    else:
        print("Unknown output format: %s" % (output))
        exit(1)
        
    print("Saved %s" % (output))

    
if __name__ == "__main__":
    main(sys.argv[1:])