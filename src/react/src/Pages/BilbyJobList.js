import React from "react";
import {Grid, Header, Segment, Dropdown} from "semantic-ui-react";
import {harnessApi} from "../index";
import JobList from "../Components/List/JobList";
import { graphql, createPaginationContainer } from "react-relay";
import _ from "lodash";

const RECORDS_PER_PAGE = 2;

class BilbyJobList extends React.Component {
    constructor(props) {
        super(props);
        
        this.state = {
            page: 5,
            loading: false,
        }

        this.debouncedScroll =  _.debounce(this.handleScroll,100)
    }

    componentDidMount() {
        window.addEventListener('scroll', this.debouncedScroll)
    }

    componentWillUnmount() {
        window.removeEventListener('scroll', this.debouncedScroll)
    }


    handleScroll = () => {
        const wrappedElement = document.getElementById('scrollable');
        if (wrappedElement.getBoundingClientRect().bottom <= window.innerHeight) {
            this.loadMore()
        }
    }

    loadMore() {
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
        return (
            <React.Fragment>
                <Header as='h2' attached='top'>Bilby Job List</Header>
                <Segment attached id='scrollable'>
                    <Grid centered textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                        <JobList jobs={this.props.data.bilbyJobs} handleSort={this.handleSort} {...this.props}/>
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
                    after: $cursor,
                    orderBy: $orderBy
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
                $cursor: String,
                $orderBy: String
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

        getVariables(props, {count, cursor}, {orderBy}) {
            return {
                count,
                cursor,
                orderBy,
            }
        }
    }
)