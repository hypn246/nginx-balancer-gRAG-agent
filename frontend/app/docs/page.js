import React from "react";
import Navbar from "../../components/Navbar";

function Docs() {
  return (
    <>
      <Navbar />
      <main className="m-8 mt-32 ">
        <div className="center mt-5 mb-3">
          <h1 className="text-center text-4xl ">How to use this web?</h1>
        </div>
        <p>This website using gRAG with LLM fot better result in solving load balaincing problem with Nginx technology</p>
        <p>
          It will recived some sort of data like in the{" "}
          <a className="underline p-1 bg-emerald-300 rounded-md" href="/example">
            /example
          </a>{" "}
          then it will give result include: <br />- Analysis <br />- Suggest load balancing method (of Nginx)
          <br />- Suggested Nginx config
          <br />- And exmplaination for that configuration
        </p>
        <div className="flex flex-col">
          <h2 className="font-bold text-xl my-4">Command: </h2>
          <p className="my-5">
            <span className="p-2 bg-gray-300 rounded-md">/grag:</span> Used in the first of the prompt for the gRAG query
          </p>
          <p className="my-5">
            <span className="p-2 bg-gray-300 rounded-md">/pro:</span> Used in the first of the prompt for the Prometheus API metrics collector query
          </p>
        </div>
      </main>
    </>
  );
}

export default Docs;
