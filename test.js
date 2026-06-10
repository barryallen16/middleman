// ============== CONFIGURATION ==============

const CONFIG = {
  API_BASE_URL: "https://middleman-git-api-jayadithyas-projects-46b8b61e.vercel.app",
  MAX_FILE_SIZE: 5 * 1024 * 1024, // 5MB
  ALLOWED_TYPES: ["image/png", "image/jpg", "image/jpeg"],
  REQUEST_TIMEOUT: 120000, 
};

// ============== ERROR CLASSES ==============

class AppError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.code = code;
    this.details = details;
    this.name = "AppError";
  }
}

class NetworkError extends AppError {
  constructor(message = "Unable to connect to server") {
    super("NETWORK_ERROR", message);
    this.name = "NetworkError";
  }
}

class ValidationError extends AppError {
  constructor(message, details = {}) {
    super("VALIDATION_ERROR", message, details);
    this.name = "ValidationError";
  }
}

class APIError extends AppError {
  constructor(code, message, details = {}, statusCode = 500) {
    super(code, message, details);
    this.statusCode = statusCode;
    this.name = "APIError";
  }
}

// ============== ERROR MESSAGES MAP ==============

const ERROR_MESSAGES = {
  NETWORK_ERROR: "Couldn't reach the server. Check your internet connection.",
  TIMEOUT_ERROR: "Request timed out. The server is taking too long.",
  VALIDATION_ERROR: "Invalid input. Please check your data and try again.",
  INVALID_FILE_TYPE: "Invalid file type. Please upload a PNG, JPG, or JPEG.",
  FILE_TOO_LARGE: "File is too large. Maximum allowed size is 5MB.",
  EMPTY_FILE: "The uploaded file is empty.",
  OCR_ERROR: "Couldn't read the image. Please upload a clearer screenshot.",
  IMAGE_UNCLEAR: "The image is too blurry. Please upload a better quality image.",
  SUBJECT_NOT_FOUND: "Some subjects in your result weren't recognized.",
  NO_RESULTS: "No valid results found. Ensure you're uploading a results screenshot.",
  STUDENT_NOT_FOUND: "No existing data found for this register number.",
  INTERNAL_ERROR: "Something went wrong on our end. Please try again later.",
  EXTERNAL_SERVICE_ERROR: "Our AI service is temporarily unavailable.",
  UNKNOWN_ERROR: "An unexpected error occurred. Please try again.",
};

// ============== DOM ELEMENTS ==============

const elements = {
  // Navigation
  navCalc: document.getElementById("nav-calc"),
  navPrev: document.getElementById("nav-prev"),
  navSearch: document.getElementById("nav-search"),
  
  // Views
  viewCalc: document.getElementById("view-calc"),
  viewPrev: document.getElementById("view-prev"),
  viewSearch: document.getElementById("view-search"),
  selectRegScreen: document.getElementById("select-regscreen"),
  resultSection: document.getElementById("results"),

  // Data Displays
  studentName: document.getElementById("stdname"),
  studentRegno: document.getElementById("stdregno"),
  resultDisplay: document.getElementById("resultDisplay"),
  
  // Calculate Controls
  dropZone: document.getElementById("dropzone"),
  preview: document.getElementById("preview"),
  fileInput: document.getElementById("file-input"),
  clrBtn: document.getElementById("clear-btn"),
  calBtn: document.getElementById("cal-btn"),
  uploadText: document.getElementById("upload-text"),

  // Prev Data Controls
  prevRegno: document.getElementById("prev-regno"),
  prevCgpa: document.getElementById("prev-cgpa"),
  prevCredits: document.getElementById("prev-credits"),
  saveManualPrev: document.getElementById("save-manual-prev"),
  prevDropzone: document.getElementById("prev-dropzone"),
  prevFileInput: document.getElementById("prev-file-input"),

  // Search Controls
  searchRegno: document.getElementById("search-regno"),
  searchBtn: document.getElementById("search-btn"),

  // Globals
  loadingScreen: document.getElementById("loading-screen"),
  selectRegno: document.getElementById("select-regno"),
  viewGpa: document.getElementById("view-gpa"),
  errorMessage: document.getElementById("error-message"),
  errorToast: document.getElementById("toast-danger"),
  retryBtn: document.getElementById("retry-btn"),
  closeToastBtn: document.getElementById("close-toast-btn"),
  goBackBtn: document.getElementById("go-back-btn"),
  gotoHome: document.getElementById("go-to-home"),
};

// ============== STATE ==============

let state = {
  globalResponse: [],
  multipleStudentResults: false,
  lastFile: null,
};

// ============== VIEW LOGIC ==============

function switchView(viewName) {
  // Hide all sections
  elements.viewCalc.classList.add("hidden");
  elements.viewPrev.classList.add("hidden");
  elements.viewSearch.classList.add("hidden");
  elements.resultSection.classList.add("hidden");
  elements.selectRegScreen.classList.add("hidden");

  // Reset Nav UI
  [elements.navCalc, elements.navPrev, elements.navSearch].forEach(nav => {
    nav.classList.remove("nav-active", "text-white");
    nav.classList.add("text-white/50");
  });

  if (viewName === 'calc') {
    elements.viewCalc.classList.remove("hidden");
    elements.navCalc.classList.add("nav-active", "text-white");
    elements.navCalc.classList.remove("text-white/50");
  } else if (viewName === 'prev') {
    elements.viewPrev.classList.remove("hidden");
    elements.navPrev.classList.add("nav-active", "text-white");
    elements.navPrev.classList.remove("text-white/50");
  } else if (viewName === 'search') {
    elements.viewSearch.classList.remove("hidden");
    elements.navSearch.classList.add("nav-active", "text-white");
    elements.navSearch.classList.remove("text-white/50");
  } else if (viewName === 'results') {
    elements.resultSection.classList.remove("hidden");
  } else if (viewName === 'select-reg') {
    elements.selectRegScreen.classList.remove("hidden");
  }
}

// ============== VALIDATION ==============

function validateFile(file) {
  if (!file) throw new ValidationError("No file selected");
  if (!CONFIG.ALLOWED_TYPES.includes(file.type)) {
    throw new ValidationError(ERROR_MESSAGES.INVALID_FILE_TYPE);
  }
  if (file.size === 0) throw new ValidationError(ERROR_MESSAGES.EMPTY_FILE);
  if (file.size > CONFIG.MAX_FILE_SIZE) throw new ValidationError(ERROR_MESSAGES.FILE_TOO_LARGE);
  return true;
}

// ============== API FUNCTIONS ==============

async function fetchWithTimeout(url, options, timeout = CONFIG.REQUEST_TIMEOUT) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === "AbortError") throw new NetworkError(ERROR_MESSAGES.TIMEOUT_ERROR);
    throw error;
  }
}

async function parseAPIResponse(response) {
  const contentType = response.headers.get("content-type");
  if (!contentType || !contentType.includes("application/json")) {
    throw new APIError("INVALID_RESPONSE", "Server returned an invalid response", {}, response.status);
  }
  return await response.json();
}

async function handleAPIError(response) {
  try {
    const errorData = await parseAPIResponse(response);
    if (errorData.error) {
      const { code, message, details } = errorData.error;
      throw new APIError(code, ERROR_MESSAGES[code] || message, details, response.status);
    }
    throw new APIError("UNKNOWN_ERROR", ERROR_MESSAGES.UNKNOWN_ERROR, {}, response.status);
  } catch (error) {
    if (error instanceof APIError) throw error;
    throw new APIError("HTTP_ERROR", `Server error (${response.status})`, {}, response.status);
  }
}

// Endpoints
async function uploadImage(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetchWithTimeout(`${CONFIG.API_BASE_URL}/calculateGpa/`, { method: "POST", body: formData });
  if (!response.ok) await handleAPIError(response);
  const data = await parseAPIResponse(response);
  if (!data.success) throw new APIError(data.error.code, data.error.message);
  return data.data;
}

async function uploadPreviousImage(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetchWithTimeout(`${CONFIG.API_BASE_URL}/uploadPreviousSem/`, { method: "POST", body: formData });
  if (!response.ok) await handleAPIError(response);
  const data = await parseAPIResponse(response);
  if (!data.success) throw new APIError(data.error.code, data.error.message);
  return data.data;
}

async function searchStudentData(regno) {
  const response = await fetchWithTimeout(`${CONFIG.API_BASE_URL}/student/${regno}`, { method: "GET" });
  if (!response.ok) await handleAPIError(response);
  const data = await parseAPIResponse(response);
  if (!data.success) throw new APIError(data.error.code, data.error.message);
  return data.data;
}

async function saveManualPrevData(regno, cgpa, credits) {
  const response = await fetchWithTimeout(`${CONFIG.API_BASE_URL}/manualPreviousData/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ regno, cgpa, credits })
  });
  if (!response.ok) await handleAPIError(response);
  const data = await parseAPIResponse(response);
  if (!data.success) throw new APIError(data.error.code, data.error.message);
  return data.data;
}

// ============== UI FUNCTIONS ==============

function showLoading() {
  elements.viewCalc.classList.add("hidden");
  elements.viewPrev.classList.add("hidden");
  elements.viewSearch.classList.add("hidden");
  elements.selectRegScreen.classList.add("hidden");
  elements.resultSection.classList.add("hidden");
  elements.loadingScreen.classList.remove("hidden");
}

function hideLoading() {
  elements.loadingScreen.classList.add("hidden");
}

function showError(error) {
  hideLoading();
  switchView('calc'); // Default fallback on error
  
  let message = error.message || ERROR_MESSAGES.UNKNOWN_ERROR;
  elements.errorMessage.textContent = message;
  elements.errorToast.classList.remove("hidden");
}

function dismissError() {
  elements.errorToast.classList.add("hidden");
}

function resetUpload() {
  elements.preview.querySelectorAll("img").forEach((img) => URL.revokeObjectURL(img.src));
  elements.preview.innerHTML = "";
  elements.preview.classList.add("hidden");
  elements.uploadText.classList.remove("hidden");
  elements.fileInput.value = "";
  elements.calBtn.disabled = true;
  elements.clrBtn.disabled = true;
  state.lastFile = null;
}

function displayImagePreview(files) {
  if (!files || files.length === 0) return;
  const file = files[0];
  try {
    validateFile(file);
  } catch (error) {
    showError(error);
    resetUpload();
    return;
  }
  state.lastFile = file;
  elements.preview.innerHTML = "";
  
  const li = document.createElement("li");
  const img = document.createElement("img");
  
  elements.uploadText.classList.add("hidden");
  img.src = URL.createObjectURL(file);
  elements.preview.classList.remove("hidden");
  li.classList.add("w-full", "h-full", "p-1");
  img.classList.add("w-full", "h-full", "object-contain", "rounded-lg");
  
  li.appendChild(img);
  elements.preview.appendChild(li);
  
  elements.calBtn.disabled = false;
  elements.clrBtn.disabled = false;
}

function showSelectScreen(data) {
  hideLoading();
  state.globalResponse = data;
  state.multipleStudentResults = true;
  
  elements.selectRegno.innerHTML = "";
  data.forEach((student, index) => {
    const option = document.createElement("option");
    option.textContent = `${student.student_regno} - ${student.student_name}`;
    option.value = index;
    elements.selectRegno.appendChild(option);
  });
  
  switchView('select-reg');
}

function displayResult(data) {
  hideLoading();
  switchView('results');
  
  elements.studentRegno.textContent = data.student_regno;
  elements.studentName.textContent = data.student_name || "Unknown";
  
  let gpaDisplay = data.gpa !== undefined ? Number(data.gpa).toFixed(2) : '-';
  let curCredits = data.current_credits !== undefined ? data.current_credits : '-';
  
  let resultsHTML = `
    <li class="w-full bg-white rounded-xl flex flex-col px-6 py-6 gap-2 text-black shadow-lg">
      <div class="flex justify-between items-center w-full">
        <h2 class="text-lg font-bold">Current Semester GPA:</h2>
        <h1 class="text-3xl font-black">${gpaDisplay}</h1>
      </div>
      <div class="flex justify-between items-center w-full">
        <h2 class="text-sm text-gray-500 font-bold">Current Sem Credits:</h2>
        <h1 class="text-lg font-bold">${curCredits}</h1>
      </div>
  `;
  
  if (data.prev_cgpa !== undefined && data.prev_credits !== undefined) {
    resultsHTML += `
      <hr class="border-black/10 my-3">
      <div class="flex justify-between items-center w-full text-gray-700">
        <h2 class="text-sm font-bold">Previous CGPA:</h2>
        <h1 class="text-lg font-bold">${Number(data.prev_cgpa).toFixed(2)}</h1>
      </div>
      <div class="flex justify-between items-center w-full text-gray-700">
        <h2 class="text-sm font-bold">Previous Credits:</h2>
        <h1 class="text-lg font-bold">${data.prev_credits}</h1>
      </div>
    `;
  }

  if (data.new_cgpa !== undefined) {
    resultsHTML += `
      <hr class="border-black/10 my-3">
      <div class="flex justify-between items-center w-full text-blue-700">
        <h2 class="text-xl font-bold uppercase">New Cum. CGPA:</h2>
        <h1 class="text-4xl font-black">${Number(data.new_cgpa).toFixed(2)}</h1>
      </div>
    `;
  }
  
  resultsHTML += `</li>`;
  
  if (data.results && data.results.length > 0) {
    data.results.forEach((result) => {
      resultsHTML += `
        <li class="w-full bg-[#202020] text-white rounded-xl flex px-5 py-4 justify-between items-center gap-4 shadow-md">
          <div class="flex flex-col flex-1">
            <h2 class="text-xs text-white/50 tracking-wider mb-1">${result.subject_code}</h2>
            <h1 class="font-bold text-sm leading-tight pr-2">${result.subject_name}</h1>
          </div>
          <div class="text-center flex flex-col justify-center items-center pl-4 border-l border-white/10">
            <h1 class="text-3xl font-black text-yellow-400 leading-none">${result.grade}</h1>
            <h2 class="text-[10px] text-white/40 uppercase tracking-widest mt-1">Grade</h2>
          </div>
        </li>
      `;
    });
  } else {
    resultsHTML += `<li class="text-white/50 mt-4 text-center">No subject details available for this record.</li>`;
  }
  
  elements.resultDisplay.innerHTML = resultsHTML;
}

// ============== EVENT HANDLERS ==============

function initializeEventListeners() {
  // Navigation Tabs
  elements.navCalc.addEventListener('click', () => switchView('calc'));
  elements.navPrev.addEventListener('click', () => switchView('prev'));
  elements.navSearch.addEventListener('click', () => switchView('search'));

  // Main Dropzone
  elements.dropZone.addEventListener("click", () => elements.fileInput.click());
  elements.dropZone.addEventListener("dragover", (e) => e.preventDefault());
  elements.dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    const files = [...e.dataTransfer.items].map((item) => item.getAsFile()).filter(f => f);
    displayImagePreview(files);
  });
  elements.fileInput.addEventListener("change", (e) => displayImagePreview(e.target.files));
  
  // Calculate GPA Buttons
  elements.clrBtn.addEventListener("click", resetUpload);
  elements.calBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!elements.fileInput.files[0]) return showError(new ValidationError("Please select an image first"));
    
    showLoading();
    try {
      const results = await uploadImage(elements.fileInput.files[0]);
      if (!results || results.length === 0) throw new APIError("NO_RESULTS", ERROR_MESSAGES.NO_RESULTS);
      
      if (results.length > 1) {
        showSelectScreen(results);
      } else {
        displayResult(results[0]);
      }
    } catch (error) {
      showError(error);
    }
  });

  // Prev Data Manual Form
  elements.saveManualPrev.addEventListener("click", async () => {
    const regno = elements.prevRegno.value.trim();
    const cgpa = parseFloat(elements.prevCgpa.value);
    const credits = parseInt(elements.prevCredits.value);

    if (!regno || isNaN(cgpa) || isNaN(credits)) {
      return showError(new ValidationError("Please fill all fields correctly."));
    }

    showLoading();
    try {
      const result = await saveManualPrevData(regno, cgpa, credits);
      alert(`Success! Saved ${result.prev_cgpa} CGPA for ${result.student_regno}`);
      elements.prevRegno.value = ''; elements.prevCgpa.value = ''; elements.prevCredits.value = '';
      switchView('calc');
    } catch(error) {
      showError(error);
    }
  });

  // Prev Data Image Upload
  elements.prevDropzone.addEventListener("click", () => elements.prevFileInput.click());
  elements.prevFileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    showLoading();
    try {
      validateFile(file);
      const result = await uploadPreviousImage(file);
      alert(`Successfully Extracted! CGPA: ${result.prev_cgpa}, Credits: ${result.prev_credits}`);
      elements.prevFileInput.value = '';
      switchView('calc');
    } catch(error) {
      showError(error);
      elements.prevFileInput.value = '';
    }
  });

  // Search DB
  elements.searchBtn.addEventListener("click", async () => {
    const regno = elements.searchRegno.value.trim();
    if (!regno) return showError(new ValidationError("Please enter a register number"));

    showLoading();
    try {
      const studentData = await searchStudentData(regno);
      // Map properties to match what displayResult expects
      displayResult({
        ...studentData,
        student_regno: studentData.regno,
        student_name: studentData.name,
        gpa: studentData.current_gpa,
        results: studentData.results || []
      });
    } catch(error) {
      showError(error);
    }
  });

  // Results & Modals
  elements.viewGpa.addEventListener("click", () => {
    const selected = state.globalResponse[elements.selectRegno.value];
    if (selected) displayResult(selected);
  });
  
  elements.goBackBtn.addEventListener("click", () => {
    if (state.multipleStudentResults) switchView('select-reg');
    else switchView('calc');
  });
  
  elements.gotoHome.addEventListener("click", () => switchView('calc'));
  elements.retryBtn.addEventListener("click", () => { dismissError(); if (state.lastFile) elements.calBtn.click(); });
  elements.closeToastBtn.addEventListener("click", dismissError);
}

document.addEventListener("DOMContentLoaded", () => {
  initializeEventListeners();
  switchView('calc');
});