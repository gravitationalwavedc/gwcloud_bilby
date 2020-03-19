import React from "react";
import {Button, Grid, Header, Segment} from "semantic-ui-react";
import {harnessApi} from "../index";
import JobList from "../Components/List/JobList";
import { graphql, createPaginationContainer } from "react-relay";

const RECORDS_PER_PAGE = 2;

class BilbyJobList extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            page: 5,
            loading: false
        }
    }

    loadMore() {
        if (this.props.relay.hasMore()) {
            this.props.relay.loadMore(1);
        }
    }

    render() {
        console.log(this.props.data.bilbyJobs)

        return (
            <React.Fragment>
                <Header as='h2' attached='top'>Bilby Job Form</Header>
                <Segment attached>
                    <Grid centered textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                        <JobList bilbyJobs={this.props.data.bilbyJobs}/>
                        <Button onClick={() => this.loadMore()} content="Next"/>
                    </Grid>
                </Segment>
            </React.Fragment>
        )
    }
}

// export default BilbyJobList;
export default createPaginationContainer(BilbyJobList,
    {
        data: graphql`
            fragment BilbyJobList_data on Query {
                bilbyJobs(
                    first: $count,
                    after: $cursor
                ) @connection(key: "BilbyJobList_bilbyJobs") {
                    edges {
                        node {
                            id
                            name
                            description
                            lastUpdated
                        }
                    }
                  }
            }
        `,
    },
    {
        direction: 'forward',
        query: graphql`
            query BilbyJobListForwardQuery(
                $count: Int!,
                $cursor: String
            ) {
              ...BilbyJobList_data
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

        getVariables(props, {count, cursor}, fragmentVariables) {
            return {
                count,
                cursor,
            }
        }
    }
)