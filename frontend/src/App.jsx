import { BrowserRouter, Routes, Route } from "react-router-dom";
import Investigator from "./investigator/Investigator.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/investigator" element={<Investigator />} />
        <Route path="*" element={<p style={{ padding: 20 }}>Sender app goes here.</p>} />
      </Routes>
    </BrowserRouter>
  );
}
