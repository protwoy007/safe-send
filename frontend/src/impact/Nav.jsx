import { NavLink } from "react-router-dom";
import Icon from "../ui/icons.jsx";
import "./impact.css";

export default function Nav() {
  return (
    <>
      <nav className="shell-nav">
        <NavLink to="/" className="brand" end>
          <span className="brand-mark"><Icon name="shield" size={22} stroke={2.4} /></span>
          <span><b>Safe-Send</b><small>Recipient Risk Check</small></span>
        </NavLink>
        <div className="nav-links">
          <NavLink to="/" end><Icon name="send" size={17} /><span className="lab">Sender</span></NavLink>
          <NavLink to="/impact"><Icon name="chart" size={17} /><span className="lab">Impact</span></NavLink>
          <NavLink to="/investigator"><Icon name="eye" size={17} /><span className="lab">Investigator</span></NavLink>
        </div>
        <span className="nav-pill">Synthetic data · human in the loop</span>
      </nav>
    </>
  );
}
