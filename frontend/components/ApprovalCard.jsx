function ApprovalCard({ data, onApprove, loading }) {
  return (
    <div className="max-w-[85%] rounded-2xl border border-yellow-300 bg-yellow-50 p-4 sm:max-w-2xl">
      <p className="mb-2 font-medium text-yellow-800 w-full">{data.question}</p>
      {data.recommended_config && <pre className="w-full mb-2 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs text-green-300">{data.recommended_config}</pre>}
      {data.explanation && <p className="w-full mb-3 text-sm text-gray-700">{data.explanation}</p>}
      <div className="flex gap-2">
        <button onClick={() => onApprove(true)} disabled={loading} className="rounded-full bg-green-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50">
          Approve
        </button>
        <button onClick={() => onApprove(false)} disabled={loading} className="rounded-full bg-gray-200 px-4 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-300 disabled:opacity-50">
          Reject
        </button>
      </div>
    </div>
  );
}

export default ApprovalCard;
