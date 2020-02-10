import React from "react";
import {Route} from 'found'
import HelloAgain from "./Pages/HelloAgain";
import Hello from "./Pages/Hello";
import BilbyJobForm from "./Pages/BilbyJobForm";
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
            <Route path="another" Component={HelloAgain}/>
            <Route path="test" Component={BilbyJobForm}/>
        </Route>
    )
}

export default getRoutes;