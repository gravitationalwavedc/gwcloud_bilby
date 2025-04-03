import { Link } from 'found';
import Navbar from 'react-bootstrap/Navbar';
import Nav from 'react-bootstrap/Nav';
import { HiOutlineUserCircle, HiOutlineLogout, HiOutlineCode } from 'react-icons/hi';
import { BsKey } from 'react-icons/bs';
import GWCloudLogo from '../assets/images/GWCloud-logo-primary200.png';

const iconStyle = {
    height: '20px',
    margin: '-2px 2px 0 0',
};

const subMenu = (name) => {
    if (name) {
        return (
            <Nav>
                <Nav.Link
                    className="justify-content-end mr-3"
                    href="https://gwcloud-python.readthedocs.io/en/latest/gettingstarted.html"
                >
                    <HiOutlineCode style={iconStyle} /> Python API
                </Nav.Link>
                <Nav.Link className="justify-content-end mr-3" href="/api-token">
                    <BsKey style={iconStyle} /> API Tokens
                </Nav.Link>
                <Navbar.Text className="justify-content-end mr-3">
                    <HiOutlineUserCircle style={iconStyle} /> {name}
                </Navbar.Text>
                <Nav.Link href={`${import.meta.env.VITE_BACKEND_URL}/sso/logout/`}>
                    <HiOutlineLogout style={iconStyle} /> Logout
                </Nav.Link>
            </Nav>
        );
    }

    return (
        <Nav>
            <a href={`${import.meta.env.VITE_BACKEND_URL}/sso/login/`}>Login</a>
        </Nav>
    );
};

const Menu = ({ name }) => {
    const SubMenu = subMenu(name);
    return (
        <Navbar fixed="top">
            <Navbar.Brand className="mr-auto">
                <Link to="/" exact className="navbar-brand-link" data-testid="GWCloudLogo">
                    <img src={GWCloudLogo} style={iconStyle} />
                    GWCloud
                </Link>
            </Navbar.Brand>
            {SubMenu}
        </Navbar>
    );
};

export default Menu;
