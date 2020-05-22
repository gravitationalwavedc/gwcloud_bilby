import React from "react";
import { graphql, createPaginationContainer } from "react-relay";
import _ from "lodash";
import BaseJobList from "./BaseJobList";
import Link from "found/lib/Link";
import { Visibility, Grid } from "semantic-ui-react";

const RECORDS_PER_PAGE = 1;

class UserJobList extends React.Component {
    constructor(props) {
        super(props);
        this.routing = {
            match: this.props.match,
            router: this.props.router,
            breadcrumbPaths: [
                {name: 'Job List', path: '/bilby/job-list/'}
            ]
        }
        
        this.state = {
            page:  0,
            loading: false,
        }
    }

    loadMore = () => {
        if (this.props.relay.hasMore()) {
            this.props.relay.loadMore(RECORDS_PER_PAGE);
        }
    }

    handleSort = (order) => {
        
        const refetchVariables = {
            count: 1,
            orderBy: order
        }
        this.props.relay.refetchConnection(1, null, refetchVariables)
    }

    render() {
        const headers = [
            {key: 'name', display: 'Name'},
            {key: 'description', display: 'Description'},
            {key: 'lastUpdated', display: 'Updated'},
            {key: 'jobStatus', display: 'Status'},
            {key: null, display: 'Actions'},
        ]

        const rows = this.props.data.bilbyJobs.edges.map(({node}) => (
            [
                node.name,
                node.description,
                node.lastUpdated,
                node.jobStatus,
                <React.Fragment>
                    <Link to={{
                        pathname: '/bilby/job-form/',
                        state: {
                            jobId: node.id
                        }
                    }} activeClassName="selected" exact match={this.props.match} router={this.props.router}>
                        Copy Job and Edit
                    </Link>
                    <br/>
                    <Link to={{
                        pathname: '/bilby/job-results/' + node.id + "/",
                    }} activeClassName="selected" exact match={this.props.match} router={this.props.router}>
                        View Results
                    </Link>
                </React.Fragment>
            ]
        ))

        return (
            <Grid.Row>
                <Grid.Column>
                    <Visibility continuous onBottomVisible={this.loadMore}>
                        <BaseJobList headers={headers} rows={rows} handleSort={this.handleSort} initialSort={'lastUpdated'}/>
                    </Visibility>
                </Grid.Column>
            </Grid.Row>
        )
    }
}

export default createPaginationContainer(UserJobList,
    {
        data: graphql`
            fragment UserJobList_data on Query {
                bilbyJobs(
                    first: $count,
                    after: $cursor,
                    orderBy: $orderBy
                ) @connection(key: "UserJobList_bilbyJobs") {
                    edges {
                        node {
                            id
                            name
                            description
                            lastUpdated
                            jobStatus
                        }
                    }
                  }
            }
        `,
    },
    {
        direction: 'forward',
        query: graphql`
            query UserJobListForwardQuery(
                $count: Int!,
                $cursor: String,
                $orderBy: String
            ) {
              ...UserJobList_data
            }
        `,
        getConnectionFromProps(props) {
            return props.data && props.data.bilbyJobs
        },

        getFragmentVariables(previousVariables, totalCount) {
            return {
                ...previousVariables,
                count: totalCount
            }
        },

        getVariables(props, {count, cursor}, {orderBy}) {
            return {
                count,
                cursor,
                orderBy,
            }
        }
    }
)