%file=4.5 GB
%A = 8.9 GB

%algo='sdstream';
%algo='ifod2';
algo='ifod2act5Mfsl';

tic
A=read_mrtrix_tracks(sprintf('/home/kwj2001/colossus_shared/HCP/mniwarptest/tmp_tckgen_660951/CSD_%s_5M.tck',algo));
toc
refvolfile='/home/kwj2001/colossus_shared/HCP/mniwarptest/tmp_tckgen_660951/nodif_brain_mask.nii.gz';
Vref=read_avw(refvolfile);
[~,stdout]=call_fsl(sprintf('fslhd %s | grep sto_xyz | sed -E ''s/sto_xyz:[0-9]//''',refvolfile));
Vxfm=textscan(stdout,'%f'); 
Vxfm=reshape(cat(1,Vxfm{:}),4,4)';


Txyz2vox=inv(Vxfm);
volsize=size(Vref);

%Asift2=load('/home/kwj2001/colossus_shared/HCP/mniwarptest/tmp_tckgen_660951/CSD_ifod2_5M_sift2.txt');

%%
%Anew (int16) = 2.6 GB
Anew=cellfun(@(x)int16(round(x)),A.data,'uniformoutput',false);

%Anewu (remove sequential) = 2.07 GB
Anewu=cellfun(@(x)x([sum(abs(diff(x,[],1)),2)~=0; true],:),Anew,'uniformoutput',false);

%Anewu8 (int8) = 1.3 GB
Anewu8=cellfun(@int8,Anewu,'uniformoutput',false);

%saved Anewu8 = 440 MB

%convert to voxel INDICES after recentering to assure positive values
%this is NOT correct currently since these could be > 127
%Aidx=cellfun(@(x)sub2ind([182 218 182],x(:,1)+129,x(:,2)+129,x(:,3)+129),Anewu8,'uniformoutput',false);

%%
tic
%took 76 seconds
Alength=cellfun(@(x)sum(sqrt(sum(diff(x,[],1).^2,2))),A.data);
toc

%note: tckstats mytracks.tck -dump mytracks_length.txt only takes 11
%seconds

%note: in MNI space at least:
% 45% of fibers in IFOD2 are < 30mm!
% 30% are < 20mm

%%
% tic
% %took 123 seconds
% A1=cellfun(@(x)x(1,:),A.data,'uniformoutput',false);
% A1=cat(1,A1{:});
% 
% An=cellfun(@(x)x(end,:),A.data,'uniformoutput',false);
% An=cat(1,An{:});
% toc
% 



%%

%volsize=[91 109 91]; %2mm MNI = 902,629 voxels
%xyz2vox=[90 126 72]; %2mm MNI 
%Txyz2vox=inv([-2 0 0 90;
%    0 2 0 -126;
%    0 0 2 -72;
%    0 0 0 1]);

volsize=[182 218 182]; %1mm MNI = 7,221,032 voxels
xyz2vox=[90 126 72];
Txyz2vox=inv([-1 0 0 90;
    0 1 0 -126;
    0 0 1 -72;
    0 0 0 1]);

%volxform=[90 -126 -72];
%volcenter=[]

tic
%Avox=cellfun(@(x)[x(:,1)+xyz2vox(1)+1,x(:,2)+xyz2vox(2)+1,x(:,3)+xyz2vox(3)+1],Anewu,'uniformoutput',false);
%Avox=cellfun(@(x)affine_transform(Txyz2vox,x),A.data,'uniformoutput',false);
Avox=cellfun(@(x)[max(1,min(volsize(1),round(-1*x(:,1)+xyz2vox(1)+1))),...
    max(1,min(volsize(2),round(x(:,2)+xyz2vox(2)+1))),...
    max(1,min(volsize(3),round(x(:,3)+xyz2vox(3)+1)))],...
    Anewu,'uniformoutput',false);
toc
%% general version (ie: acpc)

%took 180 seconds
tic
% Avoxidx=cellfun(@(x)sub2ind(volsize,...
%     max(1,min(volsize(1),round(-1*x(:,1)+xyz2vox(1)+1))),...
%     max(1,min(volsize(2),round(x(:,2)+xyz2vox(2)+1))),...
%     max(1,min(volsize(3),round(x(:,3)+xyz2vox(3)+1)))),...
%     A.data,'uniformoutput',false);

Avoxidx=cellfun(@(x)sub2ind(volsize,...
    max(1,min(volsize(1),round(Txyz2vox(1,1)*x(:,1)+Txyz2vox(1,4)+1))),...
    max(1,min(volsize(2),round(Txyz2vox(2,2)*x(:,2)+Txyz2vox(2,4)+1))),...
    max(1,min(volsize(3),round(Txyz2vox(3,3)*x(:,3)+Txyz2vox(3,4)+1)))),...
    A.data,'uniformoutput',false);

sub2ind_fast=@(sz,x,y,z)x+sz(1)*y+sz(1)*sz(2)+z;
func_xyz2voxidx=@(x)sub2ind_fast(volsize,...
    max(1,min(volsize(1),round(Txyz2vox(1,1)*x(:,1)+Txyz2vox(1,4)+1))),...
    max(1,min(volsize(2),round(Txyz2vox(2,2)*x(:,2)+Txyz2vox(2,4)+1))),...
    max(1,min(volsize(3),round(Txyz2vox(3,3)*x(:,3)+Txyz2vox(3,4)+1))));
%Avoxidx2=cellfun(@(x)x([x(1:end-1)~=x(2:end); true],:),Anew,'uniformoutput',false);
toc

tic
%took 80 seconds
%need to get this BEFORE doing unique()
Avoxidx1=cellfun(@(x)x(1),Avoxidx);
AvoxidxN=cellfun(@(x)x(end),Avoxidx);
toc

%seq dupe removal took 103 seconds
tic

%note: if they revisit a voxel later, it can't create a LOGICAL sparse 
% matrix with sparse(i,j,true), but can can work with sparse(i,j,1)
%1. revisiting only happens with a little bit of jitter really (not
%expecting big loops)
%2. we already lose the order info when we go to sparse format, so just
%use unique()?
Avoxidx=cellfun(@(x)x([x(1:end-1)~=x(2:end); true],:),Avoxidx,'uniformoutput',false);
%Avoxidx=cellfun(@unique,Avoxidx,'uniformoutput',false);

toc
%%

algo='ifod2';
tic
volsize=[182 218 182]; %1mm MNI = 7,221,032 voxels
Tvox2xyz=[-1 0 0 90;
    0 1 0 -126;
    0 0 1 -72; 
    0 0 0 1];
tckfile=sprintf('/home/kwj2001/colossus_shared/HCP/mniwarptest/tmp_tckgen_660951/CSD_%s_5M.tck',algo);
Atest=mrtrix_tracks_to_sparse(tckfile,Tvox2xyz,volsize);
toc
tic
%80 seconds to create
%744M, 70 seconds to save (-v7.3... can't save > 2GB otherwise)
%15 seconds to read

tic
save('/home/kwj2001/colossus_shared/testsparse_new.mat','Atest','-v7.3');
toc
tic
Mo=load('/home/kwj2001/colossus_shared/testsparse_new.mat');
toc
%% 2mm version:
volsize=[91 109 91]; %2mm MNI = 902,629 voxels
xyz2vox=[45 63 36]; %2mm MNI 
% Txyz2vox=inv([-2 0 0 90;
%    0 2 0 -126;
%    0 0 2 -72;
%    0 0 0 1]);

%both steps took 300 seconds with sequential dupe removal
%both steps took 400 seconds with unique()
%
%took 477 seconds once I actually fixed the transform AND added endpoints
tic
Avoxidx2=cellfun(@(x)sub2ind(volsize,...
    max(1,min(volsize(1),round(-.5*x(:,1)+xyz2vox(1)+1))),...
    max(1,min(volsize(2),round( .5*x(:,2)+xyz2vox(2)+1))),...
    max(1,min(volsize(3),round( .5*x(:,3)+xyz2vox(3)+1)))),...
    A.data,'uniformoutput',false);

%need to get this BEFORE doing unique()
Avoxidx21=cellfun(@(x)x(1),Avoxidx2);
Avoxidx2N=cellfun(@(x)x(end),Avoxidx2);

%Avoxidx2=cellfun(@(x)x([x(1:end-1)~=x(2:end); true],:),Avoxidx2,'uniformoutput',false);
%Avoxidx2=cellfun(@unique,Avoxidx2,'uniformoutput',false);

toc
%%

%%
tic
%took 100 seoncds
Astreamidx2=cellfun(@(x,y)repmat(y(1),numel(x),1),Avoxidx2,num2cell(1:numel(Avoxidx2)),'uniformoutput',false);

Asp2=sparse(cat(1,Avoxidx2{:}),cat(1,Astreamidx2{:}),true,prod(volsize),numel(Avoxidx2));

%Asp2 is 900k x 5M: 1.40 GB in memory (sparse binary)
%on disk = 375 MB
toc
%%
%took 72 seconds
tic
Astreamidx=cellfun(@(x,y)repmat(y(1),numel(x),1),Avoxidx,num2cell(1:numel(Avoxidx)),'uniformoutput',false);
Asp=sparse(cat(1,Avoxidx{:}),cat(1,Astreamidx{:}),1,prod(volsize),numel(Avoxidx));
toc

%%

%took 114 seconds
tic
Asp=sparse(cat(1,Avoxidx{:}),cat(1,Astreamidx{:}),1,prod(volsize),numel(Avoxidx));
Asp_sift2=sparse(cat(1,Avoxidx{:}),cat(1,Astreamidx{:}),Asift2(cat(1,Astreamidx{:})),prod(volsize),numel(Avoxidx));
toc

%took 152 seconds for sift2 values

%5.6gb for  double
%Asp>0 is 2.36 GB for binary
%Asp>0 is 786 MB on disk (must be saved with '-v7.3'
%%
Asum=reshape(full(sum(Asp,2)),volsize);
orthogui(Asum); %tdi

Asum2=reshape(full(sum(Asp_sift2,2)),volsize);
orthogui(Asum2); %sift2_tdi

%but... they look ALMOST identical (no flattening with SIFT2)
%this is true even when I use tckmap on the MNI-warped .tck files
%jacobian issue with MNI transform? can we estimate that ?

%%
length_bins=0:10:300;
figure;
fullscreen(gcf);
for i = 1:numel(length_bins)-1
    
    V=reshape(full(sum(Asp_sift2(:,Alength>=length_bins(i) & Alength<length_bins(i+1)),2)),volsize);
    %orthogui(V,'title',sprintf('%d to %d',length_bins(i),length_bins(i+1)));
    Vx=squeeze(mean(V,1));
    %Vx=squeeze(max(V,[],1));
    %Vy=squeeze(max(V,[],2));
    %Vz=squeeze(max(V,[],3));
    subplotgrid(numel(length_bins)-1,i);
    imagesc(Vx');
    axis xy equal off tight;
    drawnow;
    title(sprintf('%d-%dmm',length_bins(i),length_bins(i+1)));
%     
%     figure;
%     subplot(2,2,1);
%     imagesc(Vx);
%     subplot(2,2,2);
%     imagesc(Vy);
%     subplot(2,2,3);
%     imagesc(Vz);
    
    %return;
    %pause;
end