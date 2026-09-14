import React from "react";

function MessageBubble({ role, content }) {
  const isUser = role === "user";

  let data = null;

  if (!isUser) {
    try {
      const parsed = typeof content === "string" ? JSON.parse(content) : content;

      if (parsed?.analysis && parsed?.recommended_method && parsed?.explanation && parsed?.nginx_configuration) {
        data = parsed;
      }
    } catch {
      // Norm text message
    }
  }

  if (data) {
    return (
      <div className="flex w-full justify-start">
        <div className="w-fit max-w-[85%] rounded-2xl bg-gray-100 px-4 py-3 text-sm leading-relaxed text-gray-800 sm:max-w-2xl">
          <h3 className="mb-2 font-semibold text-gray-900">Load Balancing Recommendation</h3>

          <p className="mb-3 whitespace-pre-wrap text-gray-700">{data.analysis}</p>

          <div className="mb-3 rounded-lg bg-blue-50 p-3">
            <p className="text-xs font-medium text-blue-600">Recommended Method</p>

            <p className="font-semibold text-blue-900">{data.recommended_method}</p>
          </div>

          <p className="mb-3 whitespace-pre-wrap text-gray-700">{data.explanation}</p>

          <p className="mb-2 font-medium text-gray-800">Nginx Configuration</p>

          <pre className="max-w-full overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs text-green-300">
            <code>{data.nginx_configuration}</code>
          </pre>
        </div>
      </div>
    );
  }

  // Normal user / assistant message
  if (isUser) {
    return (
      <div className="user-bubble flex w-full">
        <div className="bubble rounded-2xl rounded-br-md bg-blue-600 p-3 text-sm  text-white whitespace-pre-wrap break-words sm:max-w-2xl">{content}</div>
      </div>
    );
  }

  return (
    <div className="chat-bubble flex w-full justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-gray-100 p-3 text-sm  text-gray-800 whitespace-pre-wrap break-words sm:max-w-2xl">{content}</div>
    </div>
  );
}

export default MessageBubble;
