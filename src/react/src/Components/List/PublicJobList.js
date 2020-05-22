import React from "react";
import Link from "found/lib/Link";
import { createPaginationContainer, graphql } from "react-relay";
import BaseJobList from "./BaseJobList";
import { Grid } from "semantic-ui-react";

class PublicJobList extends React.Component {
    constructor(props) {
        super(props);
    }

    handleSort = (order) => {
        const refetchVariables = {
            count: 10,
            orderBy: order
        }
        this.props.relay.refetchConnection(1, null, refetchVariables)
    }

    render() {
        const headers = [
            {key: 'userId', display: 'User'},
            {key: 'name', display: 'Name'},
            {key: 'description', display: 'Description'},
            {key: null, display: 'Status'},
            {key: null, display: 'Actions'},
        ]

        const rows = this.props.data.publicBilbyJobs.edges.map(({node}) => (
            [
                node.userId,
                node.name,
                node.description,
                node.jobStatus,
                <Link to={{
                    pathname: '/bilby/job-results/' + node.id + "/",
                }} activeClassName="selected" exact match={this.props.match} router={this.props.router}>
                    View Results
                </Link>
            ]
        ))

        return (
            <Grid.Row>
                <Grid.Column>
                    <BaseJobList headers={headers} rows={rows} handleSort={this.handleSort} initialSort={'name'}/>
                </Grid.Column>
            </Grid.Row>
        )
    }
}

export default createPaginationContainer(PublicJobList,
    {
        data: graphql`
            fragment PublicJobList_data on Query {
                publicBilbyJobs(
                    first: $count,
                    after: $cursor,
                    orderBy: $orderBy
                ) @connection(key: "PublicJobList_publicBilbyJobs") {
                    edges {
                        node {
                            id
                            userId
                            name
                            description
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
            query PublicJobListForwardQuery(
                $count: Int!,
                $cursor: String,
                $orderBy: String
            ) {
              ...PublicJobList_data
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