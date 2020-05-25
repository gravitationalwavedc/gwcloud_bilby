import React from "react";
import {graphql, createPaginationContainer, createFragmentContainer} from "react-relay";
import _ from "lodash";
import BilbyBasePage from "./BilbyBasePage";
import JobResults from "../Components/Results/JobResults";
import JobParameters from "../Components/Results/JobParameters";
import { Divider } from "semantic-ui-react";

class BilbyJobResults extends React.Component {
    constructor(props) {
        super(props);
        this.routing = {
            match: this.props.match,
            router: this.props.router,
            breadcrumbPaths: [
                {name: 'Job Results', path: '/bilby/job-results/'}
            ]
        }
    }


    render() {
        console.log(this.props)
        return (
            <BilbyBasePage loginRequired title='Bilby Job Results' {...this.routing}>
                <JobParameters bilbyJobParameters={this.props.data.bilbyJob} {...this.props}/>
                <JobResults bilbyResultFiles={this.props.data.bilbyResultFiles} {...this.props}/>
            </BilbyBasePage>
        )
    }
}

export default createFragmentContainer(BilbyJobResults,
    {
        data: graphql`
            fragment BilbyJobResults_data on Query @argumentDefinitions(
                jobId: {type: "ID!"}
            ){
                bilbyResultFiles(jobId: $jobId) {
                    ...JobResults_bilbyResultFiles
                }
                
                bilbyJob (id: $jobId) {
                    ...JobParameters_bilbyJobParameters
                }
            }
        `,
    },
);
