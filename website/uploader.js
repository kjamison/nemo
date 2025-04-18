var uploadBucketName = "kuceyeski-wcm-web-upload";
var bucketRegion = "us-east-1";
var IdentityPoolId = "us-east-1:3d5d591e-9224-4321-a4dc-be72b2558b36";
var uploadFolder = "inputs";

var uploadTimer = null;
var passwordTimerInterval = 1000;
var uploadTimerInterval = 10000;
var uploadStatusSuffix = "_status.png";
var uploadTimerCount = 0;
var nemo_version_info = null;

var reslist=[];
var parclist=[];

//set default states for allref and pairwise based on whether its a parcellation or mm resolution
//For mm resolution, set a threshold where we only check the box when resolution>=THRESH  
//eg: if thresh=3, do NOT check pairwise by default for res=1 or 2, but DO check pairwise
//by default for res=3,4,5...
var default_allref_parc=true
var default_allref_res_thresh=Infinity
var default_pairwise_parc=true
var default_pairwise_parc_regioncount_thresh=1000 //do pairwise by default unless parc has >thresh regions (eg cifti91k)
var default_allref_parc_regioncount_thresh=1000 //do allref by default unless parc has >thresh regions (eg cifti91k)
var default_pairwise_res_thresh=3
var default_regionwise_keepdiag=false
var default_regionwise_keepdiag_regionthresh=30 //keep diag by default if regioncount<=thresh

var default_endpointmask_checked=true
var default_nonzerodenom_checked=false
var default_endpointmask_name="fs87bs_dil3"

var min_parc_dilation=0;
var max_parc_dilation=3;
var default_parc_dilation=1;

var is_internal_script=false;

//these atlases are deprecated since people should be using the -subj version anyway
var atlasinfo_oldavg = {'fs86avg': {name: 'FreeSurfer86-avg', thumbnail:'images/thumbnail_fs86.png',description:'Subject-averaged Desikan-Killiany (68 cortical) + aseg (18 subcortical, no brainstem).<br/>Note: Less precise than FreeSurfer86-subj', regioncount: 86},
     'cocommp438avg': {name: 'CocoMMP438-avg','thumbnail':'images/thumbnail_cocommp438.png',description:  'Subject-averaged Glasser MMP (358 cortical), aseg (12 subcortical), FreeSurfer7 thalamic nuclei (30), AAL3v1 subcort nuclei (12), AAL3v1 cerebellum (26)', regioncount: 438},
     'cocommpsuit439avg': {name: 'CocoMMPsuit439-avg','thumbnail':'images/thumbnail_cocommpsuit439.png',description:'Subject-averaged Glasser MMP (358 cortical), aseg (12 subcortical), FreeSurfer7 thalamic nuclei (30), AAL3v1 subcort nuclei (12), SUIT cerebellum (27)', regioncount: 439},
};

var atlasinfo = {};

var atlasinfo_public = {'aal': {name: 'AAL', thumbnail:'images/thumbnail_aal.png',description:'116-region cortical+subcortical (Tzourio-Mazoyer 2002)', regioncount: 116, defaultdilation: 0},
    'aal3' : {name: 'AAL3v1', thumbnail:'images/thumbnail_aal3.png',description:'166-region cortical+subcortical AAL3v1, with high-resolution midbrain ROIs (Rolls 2020)', regioncount: 166, defaultdilation: 0},
    'cc200': {name: 'CC200', thumbnail:'images/thumbnail_cc200.png',description:'200-region cortical+subcortical (Craddock 2012)', regioncount: 200, defaultdilation: 0},
    'cc400': {name: 'CC400', thumbnail:'images/thumbnail_cc400.png',description:'392-region cortical+subcortical (Craddock 2012)', regioncount: 392, defaultdilation: 0},
    'shen268': {name: 'Shen268', thumbnail:'images/thumbnail_shen268.png',description:'268-region cortical+subcortical (Shen 2013)', regioncount: 268, defaultdilation: 0},
    'fs86subj': {name: 'FreeSurfer86-subj', thumbnail:'images/thumbnail_fs86.png',description:'Subject-specific Desikan-Killiany (68 cortical) + aseg (18 subcortical, no brainstem)', regioncount: 86},
    'fs111subj': {name: 'FreeSurferSUIT111-subj', thumbnail:'images/thumbnail_fs111cereb.png',description:'Subject-specific Desikan-Killiany (68 cortical) + aseg (16 subcortical, no brainstem) + SUIT (27 cerebellar)', regioncount: 111},
    'fs191subj': {name: 'FreeSurferSUIT191-subj', thumbnail:'images/thumbnail_fs191.png',description:'Subject-specific Destrieux (aparc.a2009s) (148 cortical) + aseg (16 subcortical, no brainstem) + SUIT (27 cerebellar)', regioncount: 191},
     'cocommp438subj': {name: 'CocoMMP438-subj','thumbnail':'images/thumbnail_cocommp438.png',description:'Subject-specific Glasser MMP (358 cortical), aseg (12 subcortical), FreeSurfer7 thalamic nuclei (30), AAL3v1 subcort nuclei (12), AAL3v1 cerebellum (26)', regioncount: 438},
     'cocommpsuit439subj': {name: 'CocoMMPsuit439-subj','thumbnail':'images/thumbnail_cocommpsuit439.png',description:'Subject-specific Glasser MMP (358 cortical), aseg (12 subcortical), FreeSurfer7 thalamic nuclei (30), AAL3v1 subcort nuclei (12), SUIT cerebellum (27)', regioncount: 439},
	'cocoyeo143subj': {name: 'CocoYeo143-subj', thumbnail:'images/thumbnail_cocoyeo143.png',description:'Subject-specific 143-region with Schaefer100 (100 cortical) + aseg (16 subcortical) + SUIT (27 cerebellar) (Schaefer 2018)', regioncount: 143},
	'cocoyeo243subj': {name: 'CocoYeo243-subj', thumbnail:'images/thumbnail_cocoyeo243.png',description:'Subject-specific 243-region with Schaefer200 (200 cortical) + aseg (16 subcortical) + SUIT (27 cerebellar) (Schaefer 2018)', regioncount: 243},
	'cocoyeo443subj': {name: 'CocoYeo443-subj', thumbnail:'images/thumbnail_cocoyeo243.png',description:'Subject-specific 443-region with Schaefer400 (400 cortical) + aseg (16 subcortical) + SUIT (27 cerebellar) (Schaefer 2018)', regioncount: 443},
	'cocolaus157subj': {name: 'CocoLaus157-subj', thumbnail:'images/thumbnail_cocolaus157.png',description:'Subject-specific 157-region with Lausanne116 (114 cortical subdivisions of Desikan-Killiany,<br>reordered to group gyri and remove corpus callosum) + aseg (16 subcortical) + SUIT (27 cerebellar) (Daducci 2012)', regioncount: 157},
	'cocolaus262subj': {name: 'CocoLaus262-subj', thumbnail:'images/thumbnail_cocolaus262.png',description:'Subject-specific 262-region with Lausanne221 (219 cortical subdivisions of Desikan-Killiany,<br>reordered to group gyri and remove corpus callosum) + aseg (16 subcortical) + SUIT (27 cerebellar) (Daducci 2012)', regioncount: 262},
	'cocolaus491subj': {name: 'CocoLaus491-subj', thumbnail:'images/thumbnail_cocolaus491.png',description:'Subject-specific 491-region with Lausanne450 (448 cortical subdivisions of Desikan-Killiany,<br>reordered to group gyri and remove corpus callosum) + aseg (16 subcortical) + SUIT (27 cerebellar) (Daducci 2012)', regioncount: 491},
    'yeo7': {name: 'Yeo7', thumbnail:'images/thumbnail_yeo7.png', description:'7-network cortical-only (Yeo 2011)', regioncount: 7, defaultdilation: 0},
    'yeo17': {name: 'Yeo17', thumbnail:'images/thumbnail_yeo17.png', description:'17-network cortical-only (Yeo 2011)', regioncount: 17, defaultdilation: 0},
};

var atlasinfo_internal = {
    'fs87bssubj': {name: 'FreeSurfer87bs-subj', thumbnail:'images/thumbnail_fs87bs.png',description:'Subject-specific Desikan-Killiany (68 cortical) + aseg (19 subcortical, including brainstem)', regioncount: 87},
    'cifti91k': {name: 'HCP-2mm-cifti91k', thumbnail:'images/thumbnail_cifti91k.png',description:'Subject-specific HCP MSMAll 32k_fs_LR cifti space<br>32k L vertices + 32k R vertices + 32k subcortical voxels = 91282 endpoints (Glasser 2013)', regioncount: 91282}
};

var resinfo = {'1': {name:'1 mm', thumbnail:'images/thumbnail_res1mm.png', description:'182x218x182 (7221032 voxels), 1446468 streamline endpoint voxels', regioncount: Infinity},
    '2': {name:'2 mm', thumbnail:'images/thumbnail_res2mm.png', description:'91x109x91 (902629 voxels), 201891 streamline endpoint voxels', regioncount: Infinity},
    '3': {name:'3 mm', thumbnail:'images/thumbnail_res3mm.png', description:'61x73x61 (271633 voxels), 64823 streamline endpoint voxels', regioncount: Infinity},
    '4': {name:'4 mm', thumbnail:'images/thumbnail_res4mm.png', description:'46x55x46 (116380 voxels), 28796 streamline endpoint voxels', regioncount: Infinity},
    '5': {name:'5 mm', thumbnail:'images/thumbnail_res5mm.png', description:'37x44x37 (60236 voxels), 15550 streamline endpoint voxels', regioncount: Infinity},
    '6': {name:'6 mm', thumbnail:'images/thumbnail_res6mm.png', description:'31x37x31 (35557 voxels), 9360 streamline endpoint voxels', regioncount: Infinity},
    '7': {name:'7 mm', thumbnail:'images/thumbnail_res7mm.png', description:'26x32x26 (21632 voxels), 6103 streamline endpoint voxels', regioncount: Infinity},
    '8': {name:'8 mm', thumbnail:'images/thumbnail_res8mm.png', description:'23x28x23 (14812 voxels), 4234 streamline endpoint voxels', regioncount: Infinity},
    '9': {name:'9 mm', thumbnail:'images/thumbnail_res9mm.png', description:'21x25x21 (11025 voxels), 3054 streamline endpoint voxels', regioncount: Infinity},
    '10': {name:'10 mm', thumbnail:'images/thumbnail_res10mm.png', description:'19x22x19 (7942 voxels), 2280 streamline endpoint voxels', regioncount: Infinity},
    '20': {name:'20 mm', thumbnail:'images/thumbnail_res20mm.png', description:'10x11x10 (1100 voxels), 358 streamline endpoint voxels', regioncount: Infinity},
    '30': {name:'30 mm', thumbnail:'images/thumbnail_res30mm.png', description:'7x8x7 (392 voxels), 142 streamline endpoint voxels', regioncount: Infinity}
};

// these are more appropriately labeled as a "resolution" but needs to be processed like an atlas,
// so do everything normally but list it under the "resolution" dropdown
var atlas_to_include_as_res = ['cifti91k'];

var tracking_algo_info = {'sdstream': {text: 'Deterministic (SD_STREAM)'},
    'ifod2act': {text: 'Probabilistic (iFOD2+ACT)'},
    'sdstreamANDifod2act': {text: 'Both Probabilistic and Deterministic', default:true}
};

AWS.config.update({
    region: bucketRegion,
    credentials: new AWS.CognitoIdentityCredentials({
        IdentityPoolId: IdentityPoolId
    })
});

var s3 = new AWS.S3({
    apiVersion: "2006-03-01",
    params: { Bucket: uploadBucketName }
});

function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function timestamp(date) {
    if (date === undefined) date = new Date();
    var datestr = date.getUTCFullYear().toString() + ("0"+(date.getUTCMonth()+1)).substr(-2) + ("0"+date.getUTCDate()).substr(-2);
    var timestr = ("0"+date.getUTCHours()).substr(-2) + ("0"+date.getUTCMinutes()).substr(-2) + ("00"+date.getUTCSeconds()).substr(-2) + ("00"+date.getUTCMilliseconds()).substr(-3);
    return datestr+"_"+timestr;
}

function filesizestring(numbytes) {
    if(numbytes < 1024) {
        return numbytes.toString() + " B";
    } else if (numbytes < 1024*1024) {
        return Math.floor(numbytes/1024).toString() + " KB";
    } else {
        return Math.floor(numbytes/(1024*1024)).toString() + " MB";
    }
}

function dict2jsonkeyval(mydict){
    retlist=[];
    for(var k in mydict)
        retlist=retlist.concat({Key:k, Value:mydict[k]});
    return retlist;
}

function jsonkeyval2dict(jsonlist){
    retval={};
    for(i=0;i<jsonlist.length; i++)
        retval[jsonlist[i].Key]=jsonlist[i].Value;
    return retval;
}


function base64_encode(data){
    var str = data.reduce(function(a,b){ return a+String.fromCharCode(b) },'');
    return btoa(str).replace(/.{76}(?=.)/g,'$&\n');
}

function checkBucketStatus(bucket, key, statusdiv, password_success_message, validation_success_message) {
    if(uploadTimer==null)
        return;
    uploadTimerCount++;
    //console.log("Count: " +  uploadTimerCount.toString());
    var s3params = {Bucket: bucket, Key: key+uploadStatusSuffix};
    s3.headObject(s3params, function(err, data) {
        if(err){
            //console.log("No object yet");
            return;
        }
        //console.log("Image is here!");
        //console.log(data);
        
        s3.getObjectTagging(s3params, function(err, tagdata) {
            if (err){
                //console.log("No tags yet");
                return;
            }
            //console.log("Tag is here!");
            tags=jsonkeyval2dict(tagdata.TagSet);
            //console.log("Count: " +  uploadTimerCount.toString());
            //console.log(tags);

            var statusimgdiv = document.getElementById("uploadstatusimage");
            var email = document.getElementById("email").value;
            
            if (tags["input_checks"]=="success"){
                successMessage(validation_success_message)
                s3.getObject(s3params,function(err,file){
                    statusimgdiv.innerHTML="<div class='statusimage'>Input lesion mask</br><img src='data:image/png;base64," + base64_encode(file.Body)+"'></div>";
                });
            } else if(tags["input_checks"]=="error"){
                s3.getObject(s3params,function(err,file){
                    inputerror=JSON.parse(file.Body);
                    if(err || !inputerror["failmessage"]){
                        errorMessage("Input file error!");
                        console.log(err)
                    } else {
                        errorMessage("Input file error! "+inputerror["failmessage"]);
                    }
                });
                
            } else if(tags["password_status"]=="error"){
                errorMessage("Incorrect password!");
            } else if(tags["password_status"]=="success"){
                neutralMessage(password_success_message);
                if(uploadTimer != null)
                    clearInterval(uploadTimer);
                uploadTimerCount=0;
                uploadTimer = setInterval(function() {checkBucketStatus(bucket, key, statusdiv, password_success_message, validation_success_message);}, uploadTimerInterval);
                return;
            }
            if(uploadTimer != null)
                clearInterval(uploadTimer);
            uploadTimer=null;
            uploadTimerCount=0;
        });
    });
}

function showUploader(run_internal_script) {
    if (run_internal_script === undefined) run_internal_script = false; //is user on internal site?
    run_local_script = document.URL.startsWith("file:///"); //is user on LOCAL (testing/debugging) site?
    is_internal_script=run_internal_script;
    
    extra_html='';
    upload_note_html=['<div id="mninote" class="mninote">',
        'You can upload a single NIfTI file, or a .zip file containing up to 10 NIfTI files.<br/>',
        '</div>'].join('\n');
    
    atlasinfo=atlasinfo_public;
    
    extra_internal_options_html='';
    extra_local_options_html='';
    extra_options_html='';
    
            
    if(default_nonzerodenom_checked)
        nonzerodenomcheckstr="1"
    else
        nonzerodenomcheckstr="0"
    extra_options_html+=['<input type="checkbox" id="nonzero_denom_checkbox" name="nonzero_denom_checkbox" value="'+nonzerodenomcheckstr+'">',
            '<label for="nonzero_denom_checkbox">Only include subjects with non-zero denominator in local ratio <span style="color:red">[Experimental]</span></label><br/>'].join('\n');
    
    if(run_internal_script){
        Object.assign(atlasinfo,atlasinfo_internal);
        extra_html+=['<label for="outputlocation">Copy to S3 location: s3://</label>',
        '<input id="outputlocation" type="text" size="50" value="kuceyeski-wcm-temp/kwj2001/nemo_output"><br/><br/>',
        '<label for="coco_password">Password:</label>',
        '<input id="coco_password" type="password" value=""><br/><br/>'].join('\n');
        
        upload_note_html=['<div id="mninote" class="mninote">',
            'You can upload a single NIfTI file, or a .zip file containing multiple NIfTI files.<br/>',
            '</div>'].join('\n');
            
    
        //For now, lets only offer this option for debugging purposes
        extra_internal_options_html+=['<input type="checkbox" id="cumulative" name="cumulative" value="1">',
        '<label for="cumulative">Accumulate total hits along streamline (Much smaller ChaCo scores) <span style="color:red">[Experimental]</span></label><br/>'].join('\n');
    
    
        //For now, lets only offer this option for debugging purposes
        extra_internal_options_html+=['<input type="checkbox" id="continuous" name="continuous" value="1">',
        '<label for="continuous">Use continuous values for input lesion (do not binarize) <span style="color:red">[Experimental]</span></label><br/>'].join('\n');

    }
    

    if(run_local_script){
        extra_html+=['<input type="checkbox" id="debug" name="debug" value="1">',
        '<label for="debug">Run in debug mode</label><br/>'].join('\n');
        
        extra_html+=['<button id="add_all_atlases" onclick="addAllAtlases()">Add all atlases</button>',
        '<button id="set_all_dilations0" onclick="setAllDilations(0)">Dilation 0</button>',
        '<button id="set_all_dilations1" onclick="setAllDilations(1)">Dilation 1</button>',
        '<button id="set_all_dilations2" onclick="setAllDilations(2)">Dilation 2</button>',
        '<button id="set_all_dilations3" onclick="setAllDilations(3)">Dilation 3</button>',
        '<br/><br/>'].join('\n');
        
        
        if(default_endpointmask_checked)
            maskcheckstr="1"
        else
            maskcheckstr="0"
        extra_local_options_html+=['<input type="checkbox" id="endpointmask_checkbox" name="endpointmask_checkbox" value="'+maskcheckstr+'">',
        '<label for="endpointmask_checkbox">Ignore streamlines that terminate in white-matter</label><br/>'].join('\n');
        
    }
    
    extra_algo_html=['<label for="tracking_algorithm_select">Tractography algorithm:</label>',
    getTrackingAlgoSelectHtml("tracking_algorithm_select"),
    '<div class="algo_description">(<a href="https://github.com/kjamison/nemo?tab=readme-ov-file#select-tractography-algorithm" target="_blank">[Help]</a>, see <a href="https://mrtrix.readthedocs.io/en/latest/reference/commands/tckgen.html"  target="_blank" rel="noopener noreferrer">MRtrix3 tckgen documentation</a>)</div>',
    '<br/><br/>'].join("\n");
    
    var htmlTemplate = [
        '<div id="version" class="versiondiv"></div>',
        '<label for="email">E-mail address:</label>',
        '<input id="email" type="text" placeholder="email@address.com" size="30"><br/><br/>',
        '<label for="fileupload">MNI Lesion NIfTI file (or .zip):</label>',
        '<div class="filediv">',
        '<input id="fileupload" type="file" accept=".gz,.nii,.zip" class="fileinfo">',
        '<label id="filesize" class="fileinfo"></label>',
        '</div><br/>',
        upload_note_html,
        '<div id="mninote" class="mninote">',
        'Note: Lesion mask must be in 1mm MNI152v6 space (same as FSL <a href="https://github.com/kjamison/nemo/blob/master/website/atlases/MNI152_T1_1mm_brain.nii.gz?raw=true">MNI152_T1_1mm_brain.nii.gz</a> or SPM avg152.nii)<br/>',
        'Voxel dimension should be 182x218x182 (or 181x217x181 for SPM)<br/>',
        '</div>',
        '<div class="mninote" style="color:red">Make sure your file names do not include any identifiable information!<br/></div>',
        '<br/>',
        'General options <a href="https://github.com/kjamison/nemo?tab=readme-ov-file#general-options" target="_blank">[Help]</a>:<br/>',
        extra_options_html,
        extra_internal_options_html,
        extra_local_options_html,
        '<input type="checkbox" id="siftweights" name="siftweights" value="1" checked>',
        '<label for="siftweights">Weight streamlines by data fit (SIFT2)</label><br/>',
        '<input type="checkbox" id="smoothing" name="smoothing" value="1" checked>',
        '<label for="smoothing">Include smoothed mean images</label><br/><br/>',
        extra_algo_html,
        '<label for="addres_select">Add output resolution:</label>',
        getResolutionSelectHtml("addres_select"),
        '<a href="https://github.com/kjamison/nemo?tab=readme-ov-file#add-resolutions-and-parcellations" target="_blank">[Help]</a><br/>',
        '<label for="addparc_select">Add output parcellation:</label>',
        getParcSelectHtml("addparc_select"),
        '<a href="https://github.com/kjamison/nemo?tab=readme-ov-file#add-resolutions-and-parcellations" target="_blank">[Help]</a><br/>',
        '<div class="parcdiv_top"></div>',
        '<div id="resdiv"></div><div id="parcdiv"></div>',
        '<br/>',
        extra_html,
        '<div style="text-align:center"><button id="upload" onclick="submitMask()" class="bigbutton">Submit File</button></div>',
        '<div id="uploadstatus"></div><div id="uploadstatusimage"></div>'
    ];
    document.getElementById("app").innerHTML = htmlTemplate.join("\n");
    document.getElementById('fileupload').onclick = function(){ 
        this.value=null;
    }
    document.getElementById('fileupload').onchange = function(){
        var filesize = document.getElementById('fileupload').files[0].size;
        document.getElementById('filesize').innerHTML="(" + filesizestring(filesize) + ")";
        neutralMessage(""); //clear previous messages
    }
    addOutput("res",null,true);
    
    var gittxt=" [<a class='gitlink' href='https://github.com/kjamison/nemo#readme' target='_blank'>github docs</a>]";
    //get version info
    if(run_local_script){
        nemo_version_info={nemo_version: "LOCAL", nemo_version_date: "TODAY"};
        document.getElementById('version').innerHTML="NeMo vLOCAL"+gittxt;
    } else {
        jsonurl='config/nemo-version.json';
        let request = new XMLHttpRequest();

        request.open('GET', jsonurl+'?r='+window.btoa(Math.random().toString()));
        request.responseType = 'json'; // now we're getting a string!
        request.send();

        request.onload = function() {
            nemo_version_info=request.response;
            document.getElementById('version').innerHTML="NeMo v"+nemo_version_info['nemo_version']+" - "+nemo_version_info['nemo_version_date']+gittxt;
        }
    }
}

function updateStatusMessage(message,message_class, keep_buttons_disabled){
    let statusdiv = document.getElementById("uploadstatus");
    let statusimgdiv = document.getElementById("uploadstatusimage");
    
    statusdiv.className=message_class;
    statusdiv.innerHTML=message;
    
    if(!keep_buttons_disabled)
        document.getElementById("upload").disabled=false;
}

function successMessage(message, keep_buttons_disabled){
    updateStatusMessage(message,"statustext_good",keep_buttons_disabled);
}
function errorMessage(message,keep_buttons_disabled){
    updateStatusMessage(message,"statustext_bad",keep_buttons_disabled);
}

function neutralMessage(message,keep_buttons_disabled){
    if(message)
        updateStatusMessage(message,"statustext_neutral",keep_buttons_disabled);
    else
        updateStatusMessage(message,"statustext_blank",keep_buttons_disabled);
}


//Debugging functions
function addAllAtlases(){
    var parcsel_id="addparc_select";
    var parcsel=document.getElementById(parcsel_id);
    atlaslist=Object.keys(atlasinfo); 
    for(var i=0; i<atlaslist.length; i++){
        parcsel.value=atlaslist[i]; 
        addOutput("parc",parcsel_id); 
    }
}
function setAllDilations(dilation){
    if(dilation===undefined)
        dilation=3;
    
    var nextparc=parseInt(getNextAvailableId("addparc",1).replace("addparc",""));
    for(var i=1; i<nextparc; i++){
        var dilsel=document.getElementById("addparc"+i+"_dilselect");
        if(dilsel)
            dilsel.value=dilation
    }
}


function getTrackingAlgoSelectHtml(id){
    var htmlTemplate=['<select id="'+id+'" name="'+id+'">'];
    algonames=Object.keys(tracking_algo_info);
    for(var i=0; i<algonames.length; i++){
        selstr=""
        if(tracking_algo_info[algonames[i]]['default']){
            selstr=" selected"
        }
        htmlTemplate.push('<option value="'+algonames[i]+'"'+selstr+'>'+tracking_algo_info[algonames[i]]['text']+'</option>');
    }
    htmlTemplate.push('</select>');
    return htmlTemplate.join("\n");
}

function getResolutionSelectHtml(id){
    var htmlTemplate=['<select id="'+id+'" name="'+id+'" onchange="addOutput(\'res\',\'addres_select\',false)">'];
    htmlTemplate.push('<option value="none">[SELECT]</option>');
    resnames=Object.keys(resinfo);
    for(var i=0; i<resnames.length; i++){
        htmlTemplate.push('<option value="'+resnames[i]+'">'+resinfo[resnames[i]]['name']+'</option>');
    }
    for(var i=0; i<atlas_to_include_as_res.length; i++){
        if(!atlasinfo[atlas_to_include_as_res[i]])
            continue
        htmlTemplate.push('<option value="'+atlas_to_include_as_res[i]+'">'+atlasinfo[atlas_to_include_as_res[i]]['name']+'</option>');
    }

    htmlTemplate.push('</select>');
    return htmlTemplate.join("\n");
}

function getParcSelectHtml(id){
    var htmlTemplate=['<select id="'+id+'" name="'+id+'" onchange="addOutput(\'parc\',\'addparc_select\',false)">'];
    htmlTemplate.push('<option value="none">[SELECT]</option>');
    htmlTemplate.push('<option value="custom">[Upload custom atlas]</option>');
    atlasnames=Object.keys(atlasinfo);
    for(var i = 0; i < atlasnames.length; i++){
        if(atlas_to_include_as_res.indexOf(atlasnames[i])>=0)
            continue;
        htmlTemplate.push('<option value="'+atlasnames[i]+'">'+atlasinfo[atlasnames[i]]['name']+'</option>');
    }

    htmlTemplate.push('</select>');
    return htmlTemplate.join("\n");
}

function getParcDilationHtml(id, override_default_dilation){
    var default_dil=default_parc_dilation;
    if (override_default_dilation !== undefined)
        default_dil=override_default_dilation;
    
    var htmlTemplate=['<select id="'+id+'" name="'+id+'">'];
    
    for(var i = min_parc_dilation; i <= max_parc_dilation; i++){
        dilstring=i.toString()+"mm";
        isdefaultstring="";
        if(i==0)
            dilstring+=" (not recommended)"; 
        if(i==default_dil)
            isdefaultstring=" selected";
        htmlTemplate.push('<option value="'+i+'" '+isdefaultstring+'>'+dilstring+'</option>');
    }

    htmlTemplate.push('</select>');
    return htmlTemplate.join("\n");
}

function addOutput(parc_or_res, select_id, init1mm){
    neutralMessage(""); //clear previous messages
    var allrefchecked=""
    var pairwisechecked=""
    var keepdiagchecked=""
    var pairwise_disabled=""
    var pairwise_override_input=""

    parc_or_res_orig=parc_or_res;
    
    if(init1mm){
        var selvalue="1";
        var seltext="1 mm";
    } else {
        var myselect = document.getElementById(select_id);
        var selvalue=myselect.options[myselect.options.selectedIndex].value;
        if(selvalue=="none"){
            return;
        }
        var seltext=myselect.options[myselect.options.selectedIndex].text;
        
        if(atlasinfo[selvalue]){
            //in the case where we passed cifti parc from the "res" dropdown, proceed as parc
            parc_or_res='parc';
        }
    }
    
    //if regioncount is available for this output, retrieve the value. We will use it 
    //to decide if keepdiag should be checked (eg: for Yeo7)
    regioncount=Infinity;
    if (atlasinfo[selvalue]){
        regioncount=atlasinfo[selvalue]["regioncount"];
    } else if (resinfo[selvalue]) {
        regioncount=resinfo[selvalue]["regioncount"];
    }
    
    //by default, only set "allref" for parcellations
    if(parc_or_res=="parc"){
        if(default_allref_parc && regioncount<=default_allref_parc_regioncount_thresh) allrefchecked="checked";
        if(default_pairwise_parc && regioncount<=default_pairwise_parc_regioncount_thresh) pairwisechecked="checked";
        if(default_regionwise_keepdiag || regioncount<=default_regionwise_keepdiag_regionthresh) keepdiagchecked="checked";
    } else if(parc_or_res=="res"){
        if(selvalue>=default_allref_res_thresh) allrefchecked="checked";
        if(selvalue>=default_pairwise_res_thresh) pairwisechecked="checked";
        if(selvalue<default_pairwise_res_thresh) pairwise_disabled=" disabled";
        if(default_regionwise_keepdiag) keepdiagchecked="checked";
        if(default_regionwise_keepdiag || regioncount<=default_regionwise_keepdiag_regionthresh) keepdiagchecked="checked";
    }
    
    if(select_id)
        document.getElementById(select_id).selectedIndex=0;
    if (parc_or_res=="parc" && selvalue != "custom" ){
        if(parclist.indexOf(selvalue)>=0)
            return;
        parclist.push(selvalue);
    } else if (parc_or_res=="res"){
        if(reslist.indexOf(selvalue)>=0)
            return;
        reslist.push(selvalue);
    }
    var parentdiv = document.getElementById(parc_or_res_orig+"div");
    
    var newid=getNextAvailableId("add"+parc_or_res,1);
    var newindex=newid.replace("add"+parc_or_res,"");
    
    var newdiv = document.createElement("div");
    newdiv.className="parcdiv";
    newdiv.id=newid; 
    
    var newfileinput_id=null;
    var newfilelabel_id=null;
    
    var dilsel_html="";
    
    htmlTemplate=[];
    htmlTemplate.push('<button onclick="removeOutput(\''+newid+'\')" style="float:right">X</button>');
    if (parc_or_res == "parc") {
        var dilsel_thisdefault=null;
        
        if (selvalue=="custom") {
            newfileinput_id=newid+'_fileupload';
            newfilelabel_id=newid+'_filesize';
            newparctext="parc"+("000000"+newindex).substr(-3);
            htmlTemplate.push('<b>Custom parcellation name: </b>',
            '<input id="'+newid+'_customname" type="text" size="25" value="'+newparctext+'">',
            '<br/><br/>',
            '<input id="'+newfileinput_id+'" type="file" accept=".gz,.nii" class="fileinfo">',
            '<label id="'+newfilelabel_id+'" class="fileinfo"></label>');
        } else {
            if(atlasinfo[selvalue] && atlasinfo[selvalue]['thumbnail'])
                htmlTemplate.push('<div style="float:right; padding-right: 20pt"><a href="'+atlasinfo[selvalue]['thumbnail'].replace(".png","_large.png")+'" target="_blank"><img src="'+atlasinfo[selvalue]['thumbnail']+'"></a></div>');
            var parc_description=""
            if (atlasinfo[selvalue]['description'])
                parc_description="<br/><div class='parcdiv_description'>"+atlasinfo[selvalue]['description']+'</div>';
            
            if (atlasinfo[selvalue]['defaultdilation'] !== undefined){
                dilsel_thisdefault=atlasinfo[selvalue]['defaultdilation'];
            }
            seltype_txt='Parcellation';
            if (parc_or_res_orig=='res')
                seltype_txt='Resolution';
            
            htmlTemplate.push('<b>'+seltype_txt+': '+seltext+'</b>'+parc_description,
            '<input id="'+newid+'_name" type="hidden" value="'+selvalue+'">');
            
            if(atlasinfo[selvalue]['force_regioncount']){
                htmlTemplate.push('<input id="'+newid+'_forceroicount" type="hidden" value="'+atlasinfo[selvalue]['regioncount']+'">');
            }
        }
        
        var dilsel=newid+"_dilselect";
        var dilhtml_tmp=""
        if(dilsel_thisdefault != null)
            dilhtml_tmp=getParcDilationHtml(dilsel,dilsel_thisdefault);
        else
            dilhtml_tmp=getParcDilationHtml(dilsel);
        
        dilsel_html='<label for="'+dilsel+'">Dilate parcels by:</label> ' +  dilhtml_tmp + "<br>";
        


        
    } else if (parc_or_res=="res") {
        if(resinfo[selvalue] && resinfo[selvalue]['thumbnail'])
            htmlTemplate.push('<div style="float:right; padding-right: 20pt"><a href="'+resinfo[selvalue]['thumbnail'].replace(".png","_large.png")+'" target="_blank"><img src="'+resinfo[selvalue]['thumbnail']+'"></a></div>');
        
        var res_description=""
        if (resinfo[selvalue]['description'])
            res_description="<br/><div class='parcdiv_description'>"+resinfo[selvalue]['description']+'</div>';
        
        htmlTemplate.push('<b>Resolution: '+seltext+'</b>'+res_description,
        '<input id="'+newid+'_name" type="hidden" value="'+selvalue+'">');
    }
    
    
    if(pairwise_disabled && is_internal_script){
        pairwise_override_input='&nbsp;<a href="javascript:void(0);" onclick="document.getElementById(\''+newid+'_pairwise\').disabled=false;" style="color:red">[Override (not recommended)]</a>';
    }
    
    htmlTemplate.push('<br/>',
        dilsel_html,
        '<input type="checkbox" id="'+newid+'_keepdiag" name="'+newid+'_keepdiag" value="1" '+keepdiagchecked+'>',
        '<label for="'+newid+'_keepdiag">Count streamlines that start and end in the same ROI in region-wise output</label><br/>',
        
        '<input type="checkbox" id="'+newid+'_pairwise" name="'+newid+'_pairwise" value="1" '+pairwisechecked+pairwise_disabled+'>',
        '<label for="'+newid+'_pairwise">Compute pairwise disconnectivity</label>'+pairwise_override_input+'<br/>',
        
        '<input type="checkbox" id="'+newid+'_output_allref" name="'+newid+'_output_allref" value="1" '+allrefchecked+'>',
        '<label for="'+newid+'_output_allref">Output ChaCo for each reference subject (large file size)</label><br/>');
    
    //    '<input type="checkbox" id="'+newid+'_output_denom" name="'+newid+'_output_denom" value="1" checked>',
    //    '<label for="'+newid+'_output_denom">Output denominator for each reference subject (large file size. Useful for re-parcellation)</label>');
    
    
    newdiv.innerHTML=htmlTemplate.join("\n");
    parentdiv.appendChild(newdiv);
    
    if (newfileinput_id != null) {
        document.getElementById(newfileinput_id).onchange = function(){
            var filesize = document.getElementById(newfileinput_id).files[0].size;
            document.getElementById(newfilelabel_id).innerHTML="(" + filesizestring(filesize) + ")";
        }
    }
}

function removeOutput(id){
    var outputname=document.getElementById(id+"_name")
    if (outputname != null) {
        if (id.startsWith("addparc")){
            var idx=parclist.indexOf(outputname.value);
            if(idx>=0)
                parclist.splice(idx,1);
        } else if(id.startsWith("addres")) {
            var idx=reslist.indexOf(outputname.value);
            if(idx>=0)
                reslist.splice(idx,1);
        }
    }
    document.getElementById(id).remove();
    neutralMessage(""); //clear previous messages
}

function getNextAvailableId(idprefix,startindex){
    var i=startindex;
    while(document.getElementById(idprefix+i)!=null)
        i++;
    return idprefix+i;
}

function submitMask() {
    if(uploadTimer != null){
        clearInterval(uploadTimer); 
        uploadTimer=null;
    }

    var files = document.getElementById("fileupload").files;
    var email = document.getElementById("email").value;
    var smoothing = document.getElementById("smoothing").checked;
    var siftweights = document.getElementById("siftweights").checked;
    var statusdiv = document.getElementById("uploadstatus");
    var statusimgdiv = document.getElementById("uploadstatusimage");
    var outputlocation = document.getElementById("outputlocation");
    var cocopassword = document.getElementById("coco_password");
    var debug_input = document.getElementById("debug");

    var cumulative = false;
    if(document.getElementById("cumulative"))
        cumulative = document.getElementById("cumulative").checked;
    
    var continuous = false;
    if(document.getElementById("continuous"))
        continuous = document.getElementById("continuous").checked;
    
    var tracking_algo = null
    if(document.getElementById("tracking_algorithm_select"))
        tracking_algo=document.getElementById("tracking_algorithm_select").value;
    
    var nonzerodenom = false;
    if(document.getElementById("nonzero_denom_checkbox"))
        nonzerodenom = document.getElementById("nonzero_denom_checkbox").checked;
        
        
    //endpointmask_name="fs87bs_dil3";
    var endpointmask_name = null
    if(document.getElementById("endpointmask_checkbox") && document.getElementById("endpointmask_checkbox").checked)
            endpointmask_name=default_endpointmask_name
    
    
    neutralMessage("...",true);
    document.getElementById("upload").disabled=true;
    statusimgdiv.innerHTML="";
    
    var uploadFolderKey = encodeURIComponent(uploadFolder) + "/";
    var newTimestamp=timestamp() 
    
    var outputs_taglist=[];
    var outputs_prefixlist=[];
    
    var resdivchildren = document.getElementById("resdiv").childNodes;
    var parcdivchildren = document.getElementById("parcdiv").childNodes;
    var resparc=Array.prototype.slice.call(resdivchildren).concat(Array.prototype.slice.call(parcdivchildren));
    
    if(resparc.length == 0){
        errorMessage("Please add at least one output resolution or parcellation.");
        return;
    }
    
    for(var i=0; i<resparc.length; i++){
        var this_id=resparc[i].id;
        var this_pairwise=document.getElementById(this_id+"_pairwise").checked;
        var this_output_allref=document.getElementById(this_id+"_output_allref").checked;
        var this_keepdiag=document.getElementById(this_id+"_keepdiag").checked;
        var this_dilselect=document.getElementById(this_id+"_dilselect");
        var this_customname=document.getElementById(this_id+"_customname");
        var this_name=document.getElementById(this_id+"_name");
        var this_filenode=document.getElementById(this_id+"_fileupload");
        var this_forceroicount=document.getElementById(this_id+"_forceroicount");
        
        if(this_customname != null)
            this_name=this_customname.value;
        else
            this_name=this_name.value;
        
        if(this_dilselect != null)
            this_dilation=this_dilselect.value;
        else
            this_dilation=null
        
        this_forceroicount_value=null
        if(this_forceroicount != null)
            this_forceroicount_value=this_forceroicount.value;
            
        var this_newkey=""
        if (this_filenode != null){
            if(!this_filenode.files.length){
                errorMessage("Please choose a parcellation file to upload first!")
                return;
            }
            var this_file=this_filenode.files[0];
            var this_filename=this_file.name;
            var this_lowername=this_filename.toLowerCase();
            var this_fileext="";
            if(this_lowername.endsWith(".nii.gz"))
                this_fileext=".nii.gz";
            else if(this_lowername.endsWith(".nii"))
                this_fileext=".nii";
            else {
                errorMessage("Unknown file extension for "+this_filename+". Must be .nii.gz, .nii");
                return;
            }
            

            var newKey=uploadFolderKey + newTimestamp + "/" + this_name + this_fileext;
            this_newkey=newKey;
            
            var upload = new AWS.S3.ManagedUpload({
            params: {
                Bucket: uploadBucketName,
                Key: newKey,
                Body: this_file,
                ACL: "bucket-owner-full-control" 
            }});

            var promise = upload.promise();

            promise.then(
            function(data) {
                console.log("Successfully uploaded atlas file: "+this_filename)
            },
            function(err) {
                errorMessage("There was an error uploading your atlas file: "+err.message)
                console.log(err);
                return;
            });
        }
        //remove the "add"
        //var this_prefix=this_id.substr(3);
        var this_prefix=this_id;
        
        if (this_id.startsWith("addres")) {
            //res=1, pairwise, allref, 
            //addres1_pairwise=True, addres1_allref=True, addres1_res=1
            outputs_taglist=outputs_taglist.concat([{Key: this_prefix+"_res", Value: this_name}, {Key: this_prefix+"_pairwise", Value: this_pairwise}, 
                {Key: this_prefix+"_allref", Value: this_output_allref},{Key: this_prefix+"_keepdiag", Value: this_keepdiag}]);

        } else if(this_id.startsWith("addparc")) {
            //addparc1_pairwise=True, addparc1_allref=True, addparc1_name=cc200, addparc1_file=parc001.nii.gz
            outputs_taglist=outputs_taglist.concat([{Key: this_prefix+"_name", Value: this_name}, {Key: this_prefix+"_pairwise", Value: this_pairwise}, 
                {Key: this_prefix+"_allref", Value: this_output_allref},{Key: this_prefix+"_keepdiag", Value: this_keepdiag}]);
            
            if(this_dilation != null)
                outputs_taglist.push({Key: this_prefix+"_dilation", Value: this_dilation});
            
            if(this_newkey.length>0)
                outputs_taglist.push({Key: this_prefix+"_filekey", Value: this_newkey});
            
            if(this_forceroicount_value != null)
                outputs_taglist.push({Key: this_prefix+"_numroi", Value: this_forceroicount_value});
        }
        outputs_prefixlist.push(this_prefix);
        //console.log(this_id, this_pairwise, this_output_allref, this_name);
    }
    if(outputs_prefixlist.length>0)
        outputs_taglist.push({Key: "output_prefix_list", Value: outputs_prefixlist.join(",")});
    //console.log(outputs_taglist);
    
    if (!files.length) {
        errorMessage("Please choose a lesion file to upload first!");
        return;
    }
    if (!email.length) {
        errorMessage("Please enter an email!")
        return;
    }
    if (cocopassword && !cocopassword.value.length) {
        errorMessage("Please enter a password!")
        return;
    }
    if (outputlocation && !outputlocation.value.length) {
        errorMessage("Please enter an S3 output location!")
        return;
    }
    
    var file = files[0];
    var fileName = file.name;

    var lowername=fileName.toLowerCase();

    var fileext=""
    if (lowername.endsWith(".nii.gz")) {
        fileext=".nii.gz"
    } else if (lowername.endsWith(".nii")) {
        fileext=".nii"
    } else if (lowername.endsWith(".zip")) {
        fileext=".zip"
    } else if (lowername.endsWith(".tar.gz")) {
        fileext=".tar.gz"
    } else if (lowername.endsWith(".tar")) {
        fileext=".tar"
    } else {
        errorMessage("Unknown file extension for "+fileName+". Must be .nii.gz, .nii, .zip, .tar, .tar.gz")
        return;
    }
    
    var newFileName=newTimestamp + "/" + uuidv4() + fileext;
    var newKey=uploadFolderKey + newFileName;

    // Use S3 ManagedUpload class as it supports multipart uploads

    // Object can only have 10 tags! Only take 
    taglist=[{Key: 'filename', Value: fileName}, {Key: 'email', Value: email},
        {Key: 'timestamp', Value: newTimestamp}, {Key: 'unixtime', Value: Date.now()}, 
        {Key: 'status_suffix', Value: uploadStatusSuffix}];

    if (debug_input) taglist.push({Key: 'debug', Value: debug_input.checked});
    
    var config_taglist=taglist.concat(dict2jsonkeyval(nemo_version_info));
    config_taglist=config_taglist.concat([{Key: 'smoothing', Value: smoothing}, {Key: 'siftweights', Value: siftweights}, {Key: 'cumulative', Value: cumulative},
        {Key: 'continuous', Value: continuous}]);
    
    if (tracking_algo)
        config_taglist=config_taglist.concat([{Key: 'tracking_algorithm', Value: tracking_algo}]);
    
    if (endpointmask_name)
        config_taglist=config_taglist.concat([{Key: 'endpointmask', Value: endpointmask_name}]);
    
    if (nonzerodenom)
        config_taglist=config_taglist.concat([{Key: 'only_nonzero_denom', Value: nonzerodenom}]);
    
    if (outputs_taglist.length)
        config_taglist=config_taglist.concat(outputs_taglist);
    
    // Add cocopassword and output location to taglist AFTER we copy taglist into config_taglist
    // so that the cocopassword is NOT in the config FILE, only in the S3 object tag
    if (cocopassword) taglist.push({Key: 'coco_password', Value: "enc:"+window.btoa(cocopassword.value)});
    if (outputlocation) taglist.push({Key: 'outputlocation', Value: outputlocation.value});
    //////////////////////////////////////////////////////////
    var jsonse=JSON.stringify(config_taglist);
    var config_blob = new Blob([jsonse], {type: "application/json"});
    
    var upload = new AWS.S3.ManagedUpload({
    params: {
        Bucket: uploadBucketName,
        Key: newKey+"_config.json",
        Body: config_blob,
        ACL: "bucket-owner-full-control" 
    }
    });

    //console.log(upload)
    var promise = upload.promise();

    promise.then(
    function(data) {
        console.log("Successfully uploaded config");
    },
    function(err) {
        errorMessage("There was an error uploading your config: "+err.message);
        console.log(err);
        return;
    });
    
    //return;
    //////////////////////////////////////////////////////////
    
    //original: ACL: 'public-read'
    var upload = new AWS.S3.ManagedUpload({
    params: {
        Bucket: uploadBucketName,
        Key: newKey,
        Body: file,
        ACL: "bucket-owner-full-control" 
    },
    tags: taglist
    });

    //console.log(upload)
    var promise = upload.promise();

    promise.then(
    function(data) {
        if(cocopassword){
            neutralMessage("Validating password...", true);
            timer_interval=passwordTimerInterval;
        } else {
            neutralMessage("Uploaded successfully!<br/>Validating inputs may take a few minutes...")
            timer_interval=uploadTimerInterval;
        }
        if(uploadTimer == null){
            uploadTimerCount=0;
            password_success_message="Uploaded successfully!<br/>Validating inputs may take a few minutes...";
            validation_success_message="Inputs validated!</br>Results with be emailed to "+email+" when complete (check spam box!)"
            uploadTimer = setInterval(function() {checkBucketStatus(uploadBucketName, newKey, statusdiv, password_success_message, validation_success_message);}, timer_interval);
        } 
    },
    function(err) {
        errorMessage("There was an error uploading your lesion mask: "+err.message);
        console.log(err);
        return;
    });
}
