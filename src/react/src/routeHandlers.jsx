import { useContext } from 'react';
import Loading from './Components/Loading';
import ReactGA from 'react-ga';
import { UserContext } from './sessionUser';

//Initialise Google Analytics
const TRACKING_ID = 'UA-219714075-1';
//If you experiencing issues with Google Analytics uncomment out the following line.
// ReactGA.initialize(trackingID, { debug: true });
// eslint-disable-next-line
ReactGA.initialize(TRACKING_ID, { testMode: process.env.NODE_ENV === 'test' });


export const handlePublicRender = (props) => {
  if (!props.Component || !props.props) {
    return <Loading />;
  }

  // Everyone loves hax
  if (props.props.location !== undefined && props.props.match === undefined) {
    props.props.match = {
      location: props.location,
    };
  }

  ReactGA.pageview(props.props.match.location.pathname);

  return <props.Component data={props.props} {...props.props} />;
};

// The extra layer of redirection means we can use hooks
export function PrivateComponent(props) {
  const user = useContext(UserContext);
  if (user === null) {
    // The user object hasn't been populated yet.
    return <Loading />;
  }
  if (!user.isAuthenticated) {
    // Redirect, but in the meantime show a loading spinner
    window.location.replace(
      `${import.meta.env.VITE_BACKEND_URL}/sso/login/?next=${import.meta.env.VITE_FRONTEND_URL}${props.match.location.pathname}`,
    );
    return <Loading />;
  } else {
    // Show a normal component
    return handlePublicRender(props);
  }
}


export const handlePrivateRender = (props) => {
  return <PrivateComponent {...props} />;
};
