import React from 'react';
import Loading from './Components/Loading';
import { RedirectException } from 'found';
import ReactGA from 'react-ga';
import { harnessApi } from './index';

//Initialise Google Analytics
const TRACKING_ID = 'UA-219714075-1';
//If you experiencing issues with Google Analytics uncomment out the following line.
// ReactGA.initialize(trackingID, { debug: true });
ReactGA.initialize(TRACKING_ID, { testMode: process.env.NODE_ENV === 'test' });

export const handlePublicRender = ({ Component, props }) => {
    if (!Component || !props) {
        return <Loading />;
    }

    // Everyone loves hax
    if (props.location !== undefined && props.match === undefined) {
        props.match = {
            location: props.location,
        };
    }

    props.isAuthenticated = harnessApi.hasAuthToken();

    ReactGA.pageview(props.match.location.pathname);

    return <Component data={props} {...props} />;
};

export const handlePrivateRender = (props) => {
    if (!harnessApi.hasAuthToken()) {
        throw new RedirectException('/auth/?next=' + props.match.location.pathname, 401);
    }

    return handlePublicRender(props);
};
