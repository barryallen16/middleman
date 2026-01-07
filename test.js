const studentName = document.getElementById("stdname");
const studentRegno = document.getElementById("stdregno");
const resultDisplay = document.getElementById("resultDisplay");
const dropZone = document.getElementById("dropzone");
const preview = document.getElementById("preview");
const fileInput = document.getElementById("file-input");
const clrbtn = document.getElementById("clear-btn");
const calbtn = document.getElementById("cal-btn");
const resultSection = document.getElementById("results");
const heroSection = document.getElementById("hero");
const loadingScreen = document.getElementById("loading-screen");
const sendImgBtn = document.getElementById("send-img");
const selectRegno = document.getElementById("select-regno");
const viewGpa = document.getElementById("view-gpa");
const selectRegScreen = document.getElementById("select-regscreen");
const errorMessage = document.getElementById("error-message");
const errorToast = document.getElementById("toast-danger");
const retryBtn = document.getElementById("retry-btn");
const closeToastBtn = document.getElementById("close-toast-btn");
const goBackBtn = document.getElementById("go-back-btn");
const gotoHome = document.getElementById("go-to-home");
const MAX_FILE_SIZE = 5 * 1024 * 1024;
const apiUploadenpoint =
  "https://middleman-ascc3ebqy-jayadithyas-projects-46b8b61e.vercel.app/";

let globalResponse = [];
let multipleStudentResults = false;

function handleMultipleResults() {
  data = globalResponse[selectRegno.value];
  displayResult(data);
  selectRegScreen.classList.add("hidden");
}

function showErrorToast(message) {
  errorMessage.textContent =
    message || "An unexcepted error occured. Try again later.";
  loadingScreen.classList.add("hidden");
  heroSection.classList.remove("hidden");
  errorToast.classList.remove("hidden");
}

function dismissError() {
  errorToast.classList.add("hidden");
  fileInput.value = "";
  preview.classList.add("hidden");
  document.getElementById("upload-text").classList.remove("hidden");
}

function displayResult(data) {
  loadingScreen.classList.add("hidden");
  resultSection.classList.remove("hidden");
  resultDisplay.innerHTML = "";
  studentRegno.textContent = data.student_regno;
  studentName.textContent = data.student_name;
  resultDisplay.innerHTML = `<li class="w-[90%] bg-white rounded-lg flex px-4 py-2 justify-between gap-4 text-black border-3">
                <h2>Your GPA is:</h2>
                <h1 class=" text-4xl font-semibold">
                  ${data.gpa}
                </h1>
          </li>`;
  data.results.forEach((result) => {
    resultDisplay.innerHTML += `<li
              class="w-[90%] bg-blue-700 rounded-lg flex px-4 py-2 justify-between gap-4 border-2 border-white"
            >
              <div><h2>${result.subject_code}</h2>
              <h1 class="font-semibold">
                ${result.subject_name}
                </h1>
              </div>
              <div class="text-center">
              <h1 class="text-4xl font-bold">${result.grade}</h1>
                <h2>Grade</h2>
              </div>
            </li>
            `;
  });
}
async function testing_response() {
  heroSection.classList.add("hidden");
  loadingScreen.classList.remove("hidden");
  const response = await fetch(apiUploadenpoint + "return/", {
    method: "GET",
  });
  let data = await response.json();
  console.log(data);
  if (data.length > 1) {
    multipleStudentResults = true;
    console.log("yes");
    globalResponse = data;
    data.forEach((stud, index) => {
      const opt = document.createElement("option");
      opt.innerHTML = stud.student_regno;
      opt.value = index;
      opt.classList.add("bg-white", "text-black", "text-sm");
      selectRegno.appendChild(opt);
    });
    loadingScreen.classList.add("hidden");
    selectRegScreen.classList.remove("hidden");
  } else if (data.length == 1) {
    displayResult(data[0]);
  } else {
    alert("error occured. try again.");
  }
}

// testing_response();
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("drop", dropHandler);
dropZone.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  if ([...e.dataTransfer.items].some((item) => item.type === "file")) {
    e.preventDefault();
  }
});

dropZone.addEventListener("dragover", (e) => {
  const fileItems = [...e.dataTransfer.items].filter(
    (item) => item.kind === "file"
  );
  if (fileItems.length > 0) {
    e.preventDefault();
    if (fileItems.some((item) => item.type.startsWith("image/"))) {
      e.dataTransfer.dropEffect = "copy";
    } else {
      e.dataTransfer.dropEffect = "none";
    }
  }
});

window.addEventListener("dragover", (e) => {
  const fileItems = [...e.dataTransfer.items].filter(
    (item) => item.kind === "file"
  );
  if (fileItems.length > 0) {
    e.preventDefault();
    if (!dropZone.contains(e.target)) {
      e.dataTransfer.dropEffect = "none";
    }
  }
});

function displayImagePreview(files) {
  if (!files || files.length === 0) {
    return;
  }
  const file = files[0];

  if (!file.type.startsWith("image/")) {
    showErrorToast("Invalid file type. Upload an image(PNG, JPG, JPEG).");
    fileInput.value = "";
    return;
  }
  if (file.size > MAX_FILE_SIZE) {
    const filesize = (file.size / (1024 * 1024)).toFixed(2);
    showErrorToast(
      `File too large (${filesize} MB). Maximum allowed size is 5 MB`
    );
    fileInput.value = "";
    return;
  }

  preview.innerHTML = "";
  const li = document.createElement("li");
  const img = document.createElement("img");
  document.getElementById("upload-text").classList.add("hidden");
  img.src = URL.createObjectURL(file);

  preview.classList.remove("hidden");
  img.classList.add("object-fill");
  li.classList.add("w-full", "h-full");
  img.classList.add("w-full", "h-full", "object-cover", "rounded-lg");
  li.appendChild(img);
  preview.appendChild(li);

  calbtn.disabled = false;
  clrbtn.disabled = false;
}

function dropHandler(ev) {
  ev.preventDefault();
  const fileItems = [...ev.dataTransfer.items]
    .map((item) => item.getAsFile())
    .filter((file) => file);
  displayImagePreview(fileItems);
}

fileInput.addEventListener("change", (e) => {
  fileInput.files = e.target.files;
  displayImagePreview(e.target.files);
});

clrbtn.addEventListener("click", (ev) => {
  for (const img of preview.querySelectorAll("img")) {
    URL.revokeObjectURL(img.src);
  }
  preview.innerHTML = "";
  preview.classList.add("hidden");
  document.getElementById("upload-text").classList.remove("hidden");
  fileInput.value = "";
  calbtn.disabled = true;
  clrbtn.disabled = true;
});

async function sendImage(e) {
  e.preventDefault();
  heroSection.classList.add("hidden");
  loadingScreen.classList.remove("hidden");
  const endpoint = apiUploadenpoint + "calculateGpa/";
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error("Upload failed");
    const data = await response.json();
    loadingScreen.classList.add("hidden");
    console.log("Success: ", data);
    if (data.length > 1) {
      multipleStudentResults = true;
      console.log("yes");
      globalResponse = data;
      data.forEach((stud, index) => {
        const opt = document.createElement("option");
        opt.innerHTML = stud.student_regno;
        opt.value = index;
        opt.classList.add("bg-white", "text-black", "text-sm");
        selectRegno.appendChild(opt);
      });
      loadingScreen.classList.add("hidden");
      selectRegScreen.classList.remove("hidden");
    } else if (data.length == 1) {
      displayResult(data[0]);
    }
  } catch (error) {
    if (error instanceof TypeError) {
      showErrorToast("Couldn't reach the server. Try again later.");
    }
  }
}
calbtn.addEventListener("click", sendImage);
sendImgBtn.addEventListener("click", testing_response);
viewGpa.addEventListener("click", handleMultipleResults);

closeToastBtn.addEventListener("click", dismissError);
retryBtn.addEventListener("click", () => {
  errorToast.classList.add("hidden");
  calbtn.click();
  ///
});

goBackBtn.addEventListener("click", () => {
  resultSection.classList.add("hidden");
  if (multipleStudentResults) {
    selectRegScreen.classList.remove("hidden");
  } else {
    heroSection.classList.remove("hidden");
  }
});

gotoHome.addEventListener("click", () => {
  selectRegScreen.classList.add("hidden");
  heroSection.classList.remove("hidden");
  while (selectRegno.firstChild) {
    selectRegno.removeChild(selectRegno.firstChild);
  }
});
