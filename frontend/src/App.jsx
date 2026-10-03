import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sender from "./sender/Sender.jsx";
import Investigator from "./investigator/Investigator.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/investigator" element={<Investigator />} />
        <Route path="*" element={<Sender />} />
      </Routes>
    </BrowserRouter>
  );
}