import React from "react";
import {Grid, Header, Segment} from "semantic-ui-react";
import {harnessApi} from "../index";
import JobList from "../Components/List/JobList";
import { graphql, createPaginationContainer } from "react-relay";

class BilbyJobList extends React.Component {
    constructor(props) {
        super(props);
        console.log(this.props)
    }

    loadMore() {

    }

    render() {
        return (
            <React.Fragment>
                <Header as='h2' attached='top'>Bilby Job Form</Header>
                <Segment attached>
                    <Grid centered textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                        <JobList bilbyJobs={this.props.bilbyJobs}/>
                    </Grid>
                </Segment>
            </React.Fragment>
        )
    }
}

// export default BilbyJobList;
export default createPaginationContainer(BilbyJobList, 
    {
        bilbyJobs: graphql`
            fragment BilbyJobList_bilbyJobs on BilbyJobNodeConnection {
                bilbyJobs(
                    first: $count,
                    after: $cursor
                ) @connection(key: BilbyJobList_bilbyJobs) {
                    edges {
                        node {
                            name,
                            description,
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
                bilbyJobs {
                    ...BilbyJobList_bilbyJobs
                }
            }
        `,
        getConnectionFromProps(props) {
            return props.jobs && props.jobs.bilbyJobs
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