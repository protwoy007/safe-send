import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sender from "./sender/Sender.jsx";
import Impact from "./impact/Impact.jsx";
import Nav from "./impact/Nav.jsx";
import Investigator from "./investigator/Investigator.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/impact" element={<Impact />} />
        <Route path="/investigator" element={<Investigator />} />
        <Route path="*" element={<Sender />} />
      </Routes>
    </BrowserRouter>
  );
}
