"use client";

import React, { useEffect, useState } from "react";
import Papa from "papaparse";
import Navbar from "../../components/Navbar";

function Example() {
  const [rows, setRows] = useState([]);
  const [sampleCount, setSampleCount] = useState(2);
  const [result, setResult] = useState([]);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Load CSV from /public/dataset.csv
  useEffect(() => {
    const loadDataset = async () => {
      try {
        setLoading(true);

        const response = await fetch("/dataset.csv");

        if (!response.ok) {
          throw new Error("Failed to load dataset.csv");
        }

        const csv = await response.text();

        Papa.parse(csv, {
          header: true,
          skipEmptyLines: true,
          dynamicTyping: true,

          complete: (parsed) => {
            setRows(parsed.data);
            setLoading(false);
          },

          error: (error) => {
            console.error(error);
            setError("Failed to parse CSV file.");
            setLoading(false);
          },
        });
      } catch (error) {
        console.error(error);
        setError("Failed to load dataset.csv");
        setLoading(false);
      }
    };

    loadDataset();
  }, []);

  const generateSamples = () => {
    if (!rows.length) return;

    const count = Math.min(Math.max(Number(sampleCount), 1), rows.length);

    // Shuffle the dataset and take the requested number of rows
    const shuffled = [...rows].sort(() => Math.random() - 0.5);

    const samples = shuffled.slice(0, count).map((row) => ({
      ip: row.ip,
      cpu_usage: Number(row.cpu_usage),
      memory_usage: Number(row.memory_usage),
      network_connection: Number(row.network_traffic),
      execution_time: Number(row.execution_time),
      latency: `${row.latency}ms`,
    }));

    setResult(samples);
    setCopied(false);
  };

  const copyResult = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(result, null, 2));

      setCopied(true);

      setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch (error) {
      console.error("Failed to copy:", error);
    }
  };

  return (
    <>
      <Navbar />
      <div className="w-full mt-28 mx-auto p-6">
        {/* Header */}
        <div className="mb-6">
          <h2 className="text-2xl font-bold">Example Generator</h2>

          <p className="mt-1 text-sm text-gray-500">Generate sample data from dataset.csv</p>
        </div>

        {/* Form */}
        <div className="rounded-lg border bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label htmlFor="sampleCount" className="mb-2 block text-sm font-medium">
                Number of samples
              </label>

              <input id="sampleCount" type="number" min="1" max={rows.length || 1} value={sampleCount} onChange={(e) => setSampleCount(e.target.value)} className="w-full rounded-md border px-3 py-2 outline-none focus:border-black" />

              {!loading && rows.length > 0 && <p className="mt-1 text-xs text-gray-500">Available samples: {rows.length}</p>}
            </div>

            <button type="button" onClick={generateSamples} disabled={loading || rows.length === 0} className="rounded-md bg-black px-5 py-2 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50">
              {loading ? "Loading..." : "Generate"}
            </button>
          </div>

          {error && <p className="mt-4 text-sm text-red-500">{error}</p>}
        </div>

        {/* Result */}
        <div className="mt-6">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Generated result</h3>

            {result.length > 0 && (
              <button type="button" onClick={copyResult} className="rounded-md border px-3 py-1.5 text-sm transition hover:bg-gray-100">
                {copied ? "Copied!" : "Copy"}
              </button>
            )}
          </div>

          <div className="min-h-[250px] overflow-auto rounded-lg bg-gray-950 p-5">{result.length > 0 ? <pre className="text-sm leading-6 text-gray-100">{JSON.stringify(result, null, 2)}</pre> : <div className="flex min-h-[210px] items-center justify-center text-sm text-gray-500">Click Generate to create samples</div>}</div>
        </div>
      </div>
    </>
  );
}

export default Example;
