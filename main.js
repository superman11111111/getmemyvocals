var dropZoneElement;
document.querySelectorAll(".drop-zone__input").forEach((inputElement) => {
  dropZoneElement = inputElement.closest(".drop-zone");

  dropZoneElement.addEventListener("click", (e) => {
    inputElement.click();
  });

  inputElement.addEventListener("change", (e) => {
    if (inputElement.files.length) {
      processUpload(dropZoneElement, inputElement.files[0]);
    }
  });

  dropZoneElement.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZoneElement.classList.add("drop-zone--over");
  });

  ["dragleave", "dragend"].forEach((type) => {
    dropZoneElement.addEventListener(type, (e) => {
      dropZoneElement.classList.remove("drop-zone--over");
    });
  });

  dropZoneElement.addEventListener("drop", (e) => {
    e.preventDefault();

    if (e.dataTransfer.files.length) {
      inputElement.files = e.dataTransfer.files;
      processUpload(dropZoneElement, e.dataTransfer.files[0]);
    }

    dropZoneElement.classList.remove("drop-zone--over");
  });
});

function start_download(uid) {
  var xhr_dl = new XMLHttpRequest();
  xhr_dl.open('GET', 'download/' + uid, true);
  xhr_dl.responseType = 'blob';
  xhr_dl.onload = function (e) {
    if (this.status == 200) {
      let contentType = xhr_dl.getResponseHeader("content-type")
      // let contentType = this.headers.get("content-type");
      // console.log(this.response)
      if (contentType === "application/json") {
        fr = new FileReader();
        fr.onload = function () {
          let jj = JSON.parse(this.result);
          // console.log(jj);
          if (jj.success == true) {
            if (jj.fileReady == false) {
              return setTimeout(function () {
                start_download(uid)
              }, 2000);
            }
          }
        };
        fr.readAsText(this.response);
      } else {
        var contentDispo = e.currentTarget.getResponseHeader('Content-Disposition');
        var fileName = contentDispo.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)[1];
        saveBlob(e.currentTarget.response, fileName)

        if (dropZoneElement.querySelector(".drop-zone__prompt")) {
          dropZoneElement.querySelector(".drop-zone__prompt").innerHTML = "Drop file here or click to upload"
        }
      }
    }
  }
  xhr_dl.send();
}

function start_process(uid) {
  var xhr = new XMLHttpRequest();
  xhr.open('POST', 'process/' + uid, true);
  xhr.onload = function () {
    if (this.status == 200) {
      var resp_process = JSON.parse(this.response);

      console.log('Server got:', resp_process);

      if (resp_process.success == true) {
        console.log(resp_process)

        start_download(uid);
      }
    }
  }
  xhr.send();
}

function saveBlob(blob, fileName) {
  var a = document.createElement('a');
  a.href = window.URL.createObjectURL(blob);
  a.download = fileName;
  a.dispatchEvent(new MouseEvent('click'));
}
/**
 * Updates the thumbnail on a drop zone element.
 *
 * @param {HTMLElement} dropZoneElement
 * @param {File} file
 */
function processUpload(dropZoneElement, file) {
  if (dropZoneElement.querySelector(".drop-zone__prompt")) {
    dropZoneElement.querySelector(".drop-zone__prompt").innerHTML = "Uploading..."
  }
  console.log(file.type)
  if (file.type.startsWith("audio/")) {
    var fd = new FormData();
    fd.append("afile", file);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', 'upload', true);
    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable) {
        var percentComplete = (e.loaded / e.total) * 100;
        console.log(percentComplete + '% uploaded');
      }
    };

    xhr.onload = function () {
      if (this.status == 200) {
        var resp_upload = JSON.parse(this.response);

        console.log('Server got:', resp_upload);

        if (resp_upload.success == true) {
          if (dropZoneElement.querySelector(".drop-zone__prompt")) {
            dropZoneElement.querySelector(".drop-zone__prompt").innerHTML = "Processing..."
          }

          start_process(resp_upload.uid);
        }
      };
    };
    xhr.send(fd);
  }
}
