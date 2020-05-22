import React from "react";
import UserJobList from "../Components/List/UserJobList";
import { graphql, createPaginationContainer, createFragmentContainer } from "react-relay";
import _ from "lodash";
import BilbyBasePage from "./BilbyBasePage";

class BilbyJobList extends React.Component {
    constructor(props) {
        super(props);
        this.routing = {
            match: this.props.match,
            router: this.props.router,
            breadcrumbPaths: [
                {name: 'Job List', path: '/bilby/job-list/'}
            ]
        }
    }

    render() {
        return (
            <BilbyBasePage loginRequired title='Bilby Job List' {...this.routing}>
                <UserJobList jobs={this.props.data.bilbyJobs} handleSort={this.handleSort} {...this.props}/>
            </BilbyBasePage>
        )
    }
}

export default createFragmentContainer(BilbyJobList, {
    data: graphql`
        fragment BilbyJobList_data on Query {
            ...UserJobList_data
        }
    `
});