import { NavLink } from "react-router-dom";
import "./impact.css";

export default function Nav() {
  return (
    <nav className="top-nav">
      <NavLink to="/" end>Sender</NavLink>
      <NavLink to="/impact">Impact</NavLink>
      <NavLink to="/investigator">Investigator</NavLink>
    </nav>
  );
}
