var uploadBucketName = "kuceyeski-wcm-web-upload";
var bucketRegion = "us-east-1";
var IdentityPoolId = "us-east-1:3d5d591e-9224-4321-a4dc-be72b2558b36";
var uploadFolder = "inputs";

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
    if (date === undefined) date = date = new Date();
    var datestr = date.getUTCFullYear().toString() + ("0"+date.getUTCMonth()).substr(-2) + ("0"+date.getUTCDate()).substr(-2);
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

function showUploader() {
    var htmlTemplate = [
      '<div>',
      'Lesion mask must be in 1mm MNI152 space (same as FSL MNI152_T1_1mm.nii.gz or SPM avg152.nii)<br/>',
      'Voxel dimension should be 182x218x182 (or 181x217x181 for SPM)<br/>',
      '</div>',
      '<br/>',
      '<label for="email">E-mail address:</label>',
      '<input id="email" type="text" value="test@test"><br/><br/>',
      '<label for="fileupload">MNI Lesion Nifti file:</label>',
      '<div class="filediv">',
      '<input id="fileupload" type="file" accept=".gz,.nii" class="fileinfo">',
      '<label id="filesize" class="fileinfo"></label>',
      '</div><br/><br/>',
      '<input type="checkbox" id="output_allref" name="output_allref" value="1" checked>',
      '<label for="output_allref">Output map for each reference subject (large file size)</label><br/><br/>',
      '<button id="upload" onclick="uploadFile()" class="uploadbutton">',
      "Upload File",
      "</button>",
      '<div id="uploadstatus"></div>'
    ];
    document.getElementById("app").innerHTML = getHtml(htmlTemplate);
    document.getElementById('fileupload').onchange = function(){
        var filesize = document.getElementById('fileupload').files[0].size;
        document.getElementById('filesize').innerHTML="(" + filesizestring(filesize) + ")";
    }
    return;
}

function uploadFile() {
  var files = document.getElementById("fileupload").files;
  var email = document.getElementById("email").value;
  var output_allref = document.getElementById("output_allref").checked;
  var statusdiv = document.getElementById("uploadstatus");
  statusdiv.className="statustext_neutral"
  statusdiv.innerHTML="..."
  if (!files.length) {
    return alert("Please choose a file to upload first.");
  }
  if (!email.length) {
    return alert("Please enter an email.");
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
      return alert("Unknown file extension for. Must be .nii.gz, .nii, .zip, .tar, .tar.gz");
  }
  
  var uploadFolderKey = encodeURIComponent(uploadFolder) + "/";
  
  var newFileName=timestamp() + "/" + uuidv4() + fileext;
  var newKey=uploadFolderKey + newFileName;

  //var photoKey = albumPhotosKey + fileName;

  // Use S3 ManagedUpload class as it supports multipart uploads

  //original: ACL: 'public-read'
  var upload = new AWS.S3.ManagedUpload({
    params: {
      Bucket: uploadBucketName,
      Key: newKey,
      Body: file,
      ACL: "bucket-owner-full-control" 
    },
	tags: [{Key: 'filename', Value: fileName}, {Key: 'email', Value: email}, {Key: 'output_allref', Value: output_allref}, {Key: 'timestamp', Value: Date.now()}]
  });

  console.log(upload)
  var promise = upload.promise();

  promise.then(
    function(data) {
      statusdiv.className="statustext_good"
      statusdiv.innerHTML="<br/>Success!"
      //alert("Successfully uploaded lesion mask.");
    },
    function(err) {
      statusdiv.className="statustext_bad"
      statusdiv.innerHTML="<br/>Failed!"
      console.log(err)
      return alert("There was an error uploading your lesion mask: ", err.message);
    }
  );
}
