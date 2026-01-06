const studentName = document.getElementById("stdname");
const studentRegno = document.getElementById("stdregno");
const resultDisplay = document.getElementById("resultDisplay");
async function testing_response() {
  response = await fetch("http://localhost:8000/test/", {
    method: "GET",
  })
    .then((response) => response.json())
    .then((data) => {
      studentRegno.textContent = data.student_regno;
      studentName.textContent = data.student_name;
      resultDisplay.innerHTML += `<li class="w-[90%] bg-white rounded-lg flex px-4 py-2 justify-between gap-4 text-black border-3">
            <h2>Your GPA is:</h2>
            <h1 class=" text-4xl font-semibold">
              ${data.gpa}
            </h1>
      </li>`;
      data.results.forEach((result) => {
        resultDisplay.innerHTML += `<li
          class="w-[90%] bg-blue-700 rounded-lg flex px-4 py-2 justify-between gap-4"
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
        // console.log(result.subject_code);
        // console.log(result.grade);
      });
    });
}
testing_response();
