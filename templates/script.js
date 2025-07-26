const recordBtn = document.getElementById("record");
const sendBtn = document.getElementById("send");
const inputField = document.getElementById("userInput");
const responseDiv = document.getElementById("response");
const languageSelect = document.getElementById("language");

const apiKey = "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"; // <- Groq API ключ

let recognition = null;

if ("webkitSpeechRecognition" in window) {
  recognition = new webkitSpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "uk-UA";

  recognition.onresult = function(event) {
    inputField.value = event.results[0][0].transcript;
  };
}

recordBtn.onclick = () => {
  if (recognition) {
    recognition.lang =
      languageSelect.value === "ru"
        ? "ru-RU"
        : languageSelect.value === "en"
        ? "en-US"
        : "uk-UA";
    recognition.start();
  }
};

sendBtn.onclick = async () => {
  const userMessage = inputField.value.trim();
  if (!userMessage) return;

  const lang = languageSelect.value || "uk";

  // Промпти по мовах
  const systemPrompt =
    lang === "ru"
      ? "Ты полезный ассистент. Отвечай чётко и кратко, без лишних слов и символов."
      : lang === "en"
      ? "You are a helpful assistant. Please respond clearly and concisely, no filler words or strange symbols."
      : "Ти корисний асистент. Відповідай чітко та коротко, без води і зайвих символів.";

  // Виводимо статус
  responseDiv.innerHTML = "⏳ Думаю...";
  sendBtn.disabled = true;
  sendBtn.innerText = "⏳ Відправка...";

  // Готуємо payload
  const payload = {
    model: "llama3-70b-8192",
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userMessage }
    ],
    temperature: 0.2,
    max_tokens: 512
    // stop: ["\n\n"] // опціонально
  };

  try {
    const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + apiKey,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error("HTTP Error: " + response.status);
    }

    const data = await response.json();
    const reply = data.choices?.[0]?.message?.content || "⚠️ Немає відповіді";

    responseDiv.innerHTML = `<div><b>🤖:</b> ${reply}</div>`;
    speak(reply, lang);
  } catch (err) {
    responseDiv.innerHTML = `⚠️ Помилка: ${err.message}`;
    console.error(err);
  } finally {
    sendBtn.disabled = false;
    sendBtn.innerText = "Відправити";
  }
};


function speak(text, lang) {
  const synth = window.speechSynthesis;
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = lang === "ru" ? "ru-RU" : lang === "en" ? "en-US" : "uk-UA";
  synth.speak(utter);
}
// Надсилання через Enter
inputField.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendBtn.click();
  }
});