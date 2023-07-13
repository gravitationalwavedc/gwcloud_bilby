import React from "react";
import ReactGA from "react-ga";
import { Route } from "found";
import MyJobs from "./Pages/MyJobs";
import PublicJobs from "./Pages/PublicJobs";
import { graphql } from "react-relay";
import { harnessApi } from "./index";
import NewJob from "./Pages/NewJob";
import DuplicateJobForm from "./Components/Forms/DuplicateJobForm";
import ViewJob from "./Pages/ViewJob";
import Loading from "./Components/Loading";
import { RedirectException } from "found";
import { INFINITE_SCROLL_CHUNK_SIZE } from "./constants";

//Initialise Google Analytics
const trackingID = "UA-219714075-1";
//If you experiencing issues with Google Analytics uncomment out the following line.
// ReactGA.initialize(trackingID, { debug: true });
ReactGA.initialize(trackingID, { testMode: process.env.NODE_ENV === "test" });

const renderTrackingRoute = (Component, props) => {
  ReactGA.pageview(props.match.location.pathname);
  return <Component data={props} {...props} />;
};

const handleRender = ({ Component, props }) => {
  if (!Component || !props) return <Loading />;

  // Everyone loves hax
  if (props.location !== undefined && props.match === undefined)
    props.match = {
      location: props.location,
    };

  if (!harnessApi.hasAuthToken())
    throw new RedirectException(
      "/auth/?next=" + props.match.location.pathname,
      401
    );

  return renderTrackingRoute(Component, props);
};

function getRoutes() {
  return (
    <Route>
      <Route
        Component={PublicJobs}
        query={graphql`
          query Routes_HomePage_Query(
            $count: Int!
            $cursor: String
            $search: String
            $timeRange: String
          ) {
            gwclouduser {
              username
            }
            ...PublicJobs_data
          }
        `}
        prepareVariables={() => ({
          timeRange: "all",
          count: INFINITE_SCROLL_CHUNK_SIZE,
        })}
        environment={harnessApi.getEnvironment("bilby")}
        render={handleRender}
      />
      <Route
        path="job-form"
        Component={NewJob}
        render={handleRender}
        query={graphql`
          query Routes_NewJob_Query {
            ...DataForm_data
          }
        `}
        environment={harnessApi.getEnvironment("bilby")}
      />
      <Route
        path="job-form/duplicate/"
        query={graphql`
          query Routes_JobForm_Query($jobId: ID!) {
            ...DuplicateJobForm_data @arguments(jobId: $jobId)
          }
        `}
        prepareVariables={(params, { location }) => ({
          jobId:
            location.state && location.state.jobId ? location.state.jobId : "",
        })}
        environment={harnessApi.getEnvironment("bilby")}
        Component={DuplicateJobForm}
        render={handleRender}
      />
      <Route
        path="job-list"
        query={graphql`
          query Routes_JobList_Query(
            $count: Int!
            $cursor: String
            $orderBy: String
          ) {
            ...MyJobs_data
          }
        `}
        prepareVariables={() => ({
          count: INFINITE_SCROLL_CHUNK_SIZE,
          timeRange: "all",
        })}
        environment={harnessApi.getEnvironment("bilby")}
        Component={MyJobs}
        render={handleRender}
      />
      <Route
        path="job-results/:jobId/"
        environment={harnessApi.getEnvironment("bilby")}
        Component={ViewJob}
        query={graphql`
          query Routes_ViewJob_Query($jobId: ID!) {
            ...ViewJob_data @arguments(jobId: $jobId)
          }
        `}
        prepareVariables={(params) => ({
          jobId: params.jobId,
        })}
        render={handleRender}
      />
    </Route>
  );
}

export default getRoutes;
