// ============== CONFIGURATION ==============

const CONFIG = {
  API_BASE_URL: "https://middleman-ascc3ebqy-jayadithyas-projects-46b8b61e.vercel.app",
  MAX_FILE_SIZE: 5 * 1024 * 1024, // 5MB
  ALLOWED_TYPES: ["image/png", "image/jpg", "image/jpeg"],
  REQUEST_TIMEOUT: 120000, // 2 minutes for OCR processing
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
  // Network errors
  NETWORK_ERROR: "Couldn't reach the server. Check your internet connection and try again.",
  TIMEOUT_ERROR: "Request timed out. The server is taking too long to respond.",
  
  // Validation errors
  VALIDATION_ERROR: "Invalid input. Please check your file and try again.",
  INVALID_FILE_TYPE: "Invalid file type. Please upload a PNG, JPG, or JPEG image.",
  FILE_TOO_LARGE: "File is too large. Maximum allowed size is 5MB.",
  EMPTY_FILE: "The uploaded file is empty.",
  
  // OCR errors
  OCR_ERROR: "Couldn't read the image. Please upload a clearer screenshot.",
  IMAGE_UNCLEAR: "The image is too blurry or unclear. Please upload a better quality image.",
  
  // Data errors
  SUBJECT_NOT_FOUND: "Some subjects in your result weren't recognized. The database may not have all subjects yet.",
  GRADE_NOT_FOUND: "Invalid grade detected in your results.",
  NO_RESULTS: "No valid results found in the image. Please ensure you're uploading a results screenshot.",
  INVALID_CREDITS: "Some subject credits are missing from our database.",
  
  // Server errors
  INTERNAL_ERROR: "Something went wrong on our end. Please try again later.",
  EXTERNAL_SERVICE_ERROR: "Our AI service is temporarily unavailable. Please try again in a few minutes.",
  
  // Default
  UNKNOWN_ERROR: "An unexpected error occurred. Please try again.",
};

// ============== DOM ELEMENTS ==============

const elements = {
  studentName: document.getElementById("stdname"),
  studentRegno: document.getElementById("stdregno"),
  resultDisplay: document.getElementById("resultDisplay"),
  dropZone: document.getElementById("dropzone"),
  preview: document.getElementById("preview"),
  fileInput: document.getElementById("file-input"),
  clrBtn: document.getElementById("clear-btn"),
  calBtn: document.getElementById("cal-btn"),
  resultSection: document.getElementById("results"),
  heroSection: document.getElementById("hero"),
  loadingScreen: document.getElementById("loading-screen"),
  selectRegno: document.getElementById("select-regno"),
  viewGpa: document.getElementById("view-gpa"),
  selectRegScreen: document.getElementById("select-regscreen"),
  errorMessage: document.getElementById("error-message"),
  errorToast: document.getElementById("toast-danger"),
  retryBtn: document.getElementById("retry-btn"),
  closeToastBtn: document.getElementById("close-toast-btn"),
  goBackBtn: document.getElementById("go-back-btn"),
  gotoHome: document.getElementById("go-to-home"),
  uploadText: document.getElementById("upload-text"),
};

// ============== STATE ==============

let state = {
  globalResponse: [],
  multipleStudentResults: false,
  lastFile: null,
};

// ============== VALIDATION FUNCTIONS ==============

function validateFile(file) {
  if (!file) {
    throw new ValidationError("No file selected");
  }

  if (!CONFIG.ALLOWED_TYPES.includes(file.type)) {
    throw new ValidationError(
      ERROR_MESSAGES.INVALID_FILE_TYPE,
      { receivedType: file.type, allowedTypes: CONFIG.ALLOWED_TYPES }
    );
  }

  if (file.size === 0) {
    throw new ValidationError(ERROR_MESSAGES.EMPTY_FILE);
  }

  if (file.size > CONFIG.MAX_FILE_SIZE) {
    const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
    throw new ValidationError(
      `File too large (${sizeMB}MB). Maximum allowed: 5MB`,
      { fileSize: sizeMB, maxSize: 5 }
    );
  }

  return true;
}

// ============== API FUNCTIONS ==============

async function fetchWithTimeout(url, options, timeout = CONFIG.REQUEST_TIMEOUT) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === "AbortError") {
      throw new NetworkError(ERROR_MESSAGES.TIMEOUT_ERROR);
    }
    throw error;
  }
}

async function parseAPIResponse(response) {
  const contentType = response.headers.get("content-type");
  
  if (!contentType || !contentType.includes("application/json")) {
    throw new APIError(
      "INVALID_RESPONSE",
      "Server returned an invalid response",
      {},
      response.status
    );
  }

  const data = await response.json();
  return data;
}

async function handleAPIError(response) {
  try {
    const errorData = await parseAPIResponse(response);
    
    if (errorData.error) {
      const { code, message, details } = errorData.error;
      const userMessage = ERROR_MESSAGES[code] || message || ERROR_MESSAGES.UNKNOWN_ERROR;
      throw new APIError(code, userMessage, details, response.status);
    }
    
    throw new APIError(
      "UNKNOWN_ERROR",
      ERROR_MESSAGES.UNKNOWN_ERROR,
      {},
      response.status
    );
  } catch (error) {
    if (error instanceof APIError) {
      throw error;
    }
    
    // Fallback for non-JSON error responses
    const statusMessages = {
      400: "Bad request. Please check your input.",
      401: "Unauthorized. Please refresh and try again.",
      403: "Access forbidden.",
      404: "Service not found.",
      422: "Could not process the image.",
      429: "Too many requests. Please wait a moment.",
      500: "Server error. Please try again later.",
      502: "Service temporarily unavailable.",
      503: "Service is overloaded. Please try again later.",
    };
    
    throw new APIError(
      "HTTP_ERROR",
      statusMessages[response.status] || `Server error (${response.status})`,
      {},
      response.status
    );
  }
}

async function uploadImage(file) {
  const endpoint = `${CONFIG.API_BASE_URL}/calculateGpa/`;
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetchWithTimeout(endpoint, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      await handleAPIError(response);
    }

    const data = await parseAPIResponse(response);
    
    if (!data.success) {
      const error = data.error || {};
      throw new APIError(
        error.code || "UNKNOWN_ERROR",
        ERROR_MESSAGES[error.code] || error.message || ERROR_MESSAGES.UNKNOWN_ERROR,
        error.details || {},
        200
      );
    }

    return data.data;
  } catch (error) {
    // Re-throw known errors
    if (error instanceof AppError) {
      throw error;
    }
    
    // Handle network errors
    if (error instanceof TypeError && error.message.includes("fetch")) {
      throw new NetworkError();
    }
    
    // Handle other errors
    console.error("Unexpected error:", error);
    throw new AppError("UNKNOWN_ERROR", ERROR_MESSAGES.UNKNOWN_ERROR);
  }
}

// ============== UI FUNCTIONS ==============

function showLoading() {
  elements.heroSection.classList.add("hidden");
  elements.selectRegScreen.classList.add("hidden");
  elements.resultSection.classList.add("hidden");
  elements.loadingScreen.classList.remove("hidden");
}

function hideLoading() {
  elements.loadingScreen.classList.add("hidden");
}

function showError(error) {
  hideLoading();
  elements.heroSection.classList.remove("hidden");
  
  let message = ERROR_MESSAGES.UNKNOWN_ERROR;
  
  if (error instanceof AppError) {
    message = error.message;
  } else if (error instanceof Error) {
    message = error.message || ERROR_MESSAGES.UNKNOWN_ERROR;
  }
  
  elements.errorMessage.textContent = message;
  elements.errorToast.classList.remove("hidden");
  
  console.error("Error details:", {
    type: error.constructor.name,
    code: error.code,
    message: error.message,
    details: error.details,
  });
}

function dismissError() {
  elements.errorToast.classList.add("hidden");
}

function resetUpload() {
  // Revoke object URLs
  elements.preview.querySelectorAll("img").forEach((img) => {
    URL.revokeObjectURL(img.src);
  });
  
  elements.preview.innerHTML = "";
  elements.preview.classList.add("hidden");
  elements.uploadText.classList.remove("hidden");
  elements.fileInput.value = "";
  elements.calBtn.disabled = true;
  elements.clrBtn.disabled = true;
  state.lastFile = null;
}

function showHero() {
  hideLoading();
  elements.selectRegScreen.classList.add("hidden");
  elements.resultSection.classList.add("hidden");
  elements.heroSection.classList.remove("hidden");
  
  // Clear select options
  while (elements.selectRegno.firstChild) {
    elements.selectRegno.removeChild(elements.selectRegno.firstChild);
  }
  
  state.globalResponse = [];
  state.multipleStudentResults = false;
}

function showSelectScreen(data) {
  hideLoading();
  state.globalResponse = data;
  state.multipleStudentResults = true;
  
  // Clear existing options
  elements.selectRegno.innerHTML = "";
  
  // Add options
  data.forEach((student, index) => {
    const option = document.createElement("option");
    option.textContent = `${student.student_regno} - ${student.student_name}`;
    option.value = index;
    option.classList.add("bg-white", "text-black", "text-sm");
    elements.selectRegno.appendChild(option);
  });
  
  elements.selectRegScreen.classList.remove("hidden");
}

function displayResult(data) {
  hideLoading();
  elements.heroSection.classList.add("hidden");
  elements.selectRegScreen.classList.add("hidden");
  elements.resultSection.classList.remove("hidden");
  
  elements.studentRegno.textContent = data.student_regno;
  elements.studentName.textContent = data.student_name;
  
  // Build results HTML
  let resultsHTML = `
    <li class="w-[90%] bg-white rounded-lg flex px-4 py-2 justify-between gap-4 text-black border-3">
      <h2>Your GPA is:</h2>
      <h1 class="text-4xl font-semibold">${data.gpa}</h1>
    </li>
  `;
  
  data.results.forEach((result) => {
    resultsHTML += `
      <li class="w-[90%] bg-blue-700 rounded-lg flex px-4 py-2 justify-between gap-4 border-2 border-white">
        <div>
          <h2>${result.subject_code}</h2>
          <h1 class="font-bold">${result.subject_name}</h1>
        </div>
        <div class="text-center">
          <h1 class="text-4xl font-bold">${result.grade}</h1>
          <h2>Grade</h2>
        </div>
      </li>
    `;
  });
  
  elements.resultDisplay.innerHTML = resultsHTML;
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
  
  // Clear previous preview
  elements.preview.innerHTML = "";
  
  const li = document.createElement("li");
  const img = document.createElement("img");
  
  elements.uploadText.classList.add("hidden");
  img.src = URL.createObjectURL(file);
  
  elements.preview.classList.remove("hidden");
  li.classList.add("w-full", "h-full");
  img.classList.add("w-full", "h-full", "object-cover", "rounded-lg");
  
  li.appendChild(img);
  elements.preview.appendChild(li);
  
  elements.calBtn.disabled = false;
  elements.clrBtn.disabled = false;
}

// ============== EVENT HANDLERS ==============

async function handleCalculateClick(e) {
  e.preventDefault();
  
  const file = elements.fileInput.files[0];
  
  if (!file) {
    showError(new ValidationError("Please select an image first"));
    return;
  }
  
  try {
    validateFile(file);
    showLoading();
    
    const results = await uploadImage(file);
    
    if (!results || results.length === 0) {
      throw new APIError("NO_RESULTS", ERROR_MESSAGES.NO_RESULTS);
    }
    
    // Store in localStorage
    if (results.length > 1) {
      localStorage.setItem("multi_result", JSON.stringify(results));
      showSelectScreen(results);
    } else {
      localStorage.setItem("single_result", JSON.stringify(results[0]));
      displayResult(results[0]);
    }
    
  } catch (error) {
    showError(error);
  }
}

function handleViewGPA() {
  const selectedIndex = elements.selectRegno.value;
  const selectedStudent = state.globalResponse[selectedIndex];
  
  if (selectedStudent) {
    localStorage.setItem("single_result", JSON.stringify(selectedStudent));
    displayResult(selectedStudent);
  }
}

function handleGoBack() {
  elements.resultSection.classList.add("hidden");
  
  if (state.multipleStudentResults) {
    elements.selectRegScreen.classList.remove("hidden");
  } else {
    showHero();
  }
}

function handleRetry() {
  dismissError();
  
  if (state.lastFile) {
    elements.calBtn.click();
  }
}

function handleDrop(e) {
  e.preventDefault();
  const files = [...e.dataTransfer.items]
    .map((item) => item.getAsFile())
    .filter((file) => file);
  displayImagePreview(files);
}

// ============== INITIALIZATION ==============

function initializeEventListeners() {
  // Drag and drop
  elements.dropZone.addEventListener("click", () => elements.fileInput.click());
  elements.dropZone.addEventListener("drop", handleDrop);
  elements.dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    const fileItems = [...e.dataTransfer.items].filter((item) => item.kind === "file");
    if (fileItems.length > 0) {
      e.dataTransfer.dropEffect = fileItems.some((item) => 
        item.type.startsWith("image/")
      ) ? "copy" : "none";
    }
  });
  
  window.addEventListener("dragover", (e) => {
    const fileItems = [...e.dataTransfer.items].filter((item) => item.kind === "file");
    if (fileItems.length > 0) {
      e.preventDefault();
      if (!elements.dropZone.contains(e.target)) {
        e.dataTransfer.dropEffect = "none";
      }
    }
  });
  
  window.addEventListener("drop", (e) => {
    if ([...e.dataTransfer.items].some((item) => item.kind === "file")) {
      e.preventDefault();
    }
  });
  
  // File input
  elements.fileInput.addEventListener("change", (e) => {
    displayImagePreview(e.target.files);
  });
  
  // Buttons
  elements.clrBtn.addEventListener("click", resetUpload);
  elements.calBtn.addEventListener("click", handleCalculateClick);
  elements.viewGpa.addEventListener("click", handleViewGPA);
  elements.goBackBtn.addEventListener("click", handleGoBack);
  elements.gotoHome.addEventListener("click", showHero);
  elements.retryBtn.addEventListener("click", handleRetry);
  elements.closeToastBtn.addEventListener("click", dismissError);
}

function checkStoredResults() {
  const singleResult = localStorage.getItem("single_result");
  
  if (singleResult) {
    try {
      const parsedResult = JSON.parse(singleResult);
      console.log("Found stored single result:", parsedResult);
      // Optionally auto-display: displayResult(parsedResult);
    } catch (e) {
      console.error("Failed to parse stored result:", e);
      localStorage.removeItem("single_result");
    }
  }
}

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  initializeEventListeners();
  checkStoredResults();
});