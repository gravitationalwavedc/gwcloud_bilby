import React from "react";
import {Route} from 'found'
import HelloAgain from "./Pages/HelloAgain";
import Hello from "./Pages/Hello";
import BilbyJobForm from "./Pages/BilbyJobForm";
import BilbyJobList from "./Pages/BilbyJobList";
import {graphql} from "react-relay";
import {harnessApi} from "./index";

function getRoutes() {
    return (
        <Route>
            <Route
                Component={Hello}
                query={graphql`
                   query Routes_UserDetails_Query {
                     gwclouduser {
                       username
                     }
                   }
                `}
                environment={harnessApi.getEnvironment('bilby')}
            />
            <Route
                Component={HelloAgain}
                query={graphql`
                   query Routes_HelloAgain_Query {
                     gwclouduser {
                       ...HelloAgain_user
                     }
                   }
                `}
                environment={harnessApi.getEnvironment('bilby')}
                path="another"
                render={({Component, props, retry, error}) => {
                    if (!Component || !props)
                        return <div>Loading...</div>;

                    return <Component user={props.gwclouduser} {...props}/>
                }}
            />
            <Route path="job-form" Component={BilbyJobForm}/>
            <Route path="job-list" 
              query={graphql`
                query Routes_JobList_Query(
                  $count: Int!,
                  $cursor: String,
                ) {
                  gwclouduser {
                    username
                  }
                  bilbyJobs (
                    first: $count,
                    after: $cursor
                  ){
                    ...BilbyJobList_bilbyJobs
                  }
                }
              `}
              prepareVariables={params => ({
                ...params,
                count: 1
              })}
              environment={harnessApi.getEnvironment('bilby')}
              Component={BilbyJobList}
              render={({Component, props, retry, error}) => {
                  if (!Component || !props)
                      return <div>Loading...</div>;

                  return <Component user={props.gwclouduser} {...props}/>
              }}/>
        </Route>
    )
}

export default getRoutes;