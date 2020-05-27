import React from "react";
import Link from "found/lib/Link";
import {createPaginationContainer, graphql} from "react-relay";
import BaseJobList from "./BaseJobList";
import {Form, Grid, Visibility} from "semantic-ui-react";
import Button from "semantic-ui-react/dist/commonjs/elements/Button";

const RECORDS_PER_PAGE = 5;

class PublicJobList extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            search: "",
            order: "name",
            timeRange: "1d"
        }
    }

    handleSort = (order) => {
        this.setState({
            ...this.state,
            order: order
        })

        const refetchVariables = {
            count: RECORDS_PER_PAGE,
            orderBy: order,
            search: this.state.search,
            timeRange: this.state.timeRange
        }
        this.props.relay.refetchConnection(1, null, refetchVariables)
    }

    handleSearchChange = (e, data) => {
        const newState = {
            ...this.state,
            [data.name]: data.value
        }
        this.setState(newState);

        const refetchVariables = {
            count: RECORDS_PER_PAGE,
            orderBy: newState.order,
            search: newState.search,
            timeRange: newState.timeRange
        }

        this.props.relay.refetchConnection(1, null, refetchVariables)
    }

    loadMore = () => {
        if (this.props.relay.hasMore()) {
            this.props.relay.loadMore(RECORDS_PER_PAGE);
        }
    }

    render() {
        const headers = [
            {key: 'userId', display: 'User'},
            {key: 'name', display: 'Name'},
            // {key: 'description', display: 'Description'},
            {key: null, display: 'Status'},
            {key: null, display: 'Actions'},
        ]

        const rows = this.props.data.publicBilbyJobs ? this.props.data.publicBilbyJobs.edges.map(({node}) => (
            [
                node.userId,
                node.name,
                // node.description,
                node.jobStatus,
                <Link to={{
                    pathname: '/bilby/job-results/' + node.id + "/",
                }} activeClassName="selected" exact match={this.props.match} router={this.props.router}>
                    View Results
                </Link>
            ]
        )) : []

        return (
            <Grid>
                <Grid.Row>
                    <Grid.Column width={1}>
                        Search
                    </Grid.Column>
                    <Grid.Column width={3}>
                        <Form.Input fluid name='search' placeholder='Search' value={this.state.search}
                                    onChange={this.handleSearchChange}/>
                    </Grid.Column>
                    <Grid.Column width={1}>
                        Time
                    </Grid.Column>
                    <Grid.Column width={3}>
                        <Form.Select name="timeRange" value={this.state.timeRange} onChange={this.handleSearchChange}
                                     options={[
                                         {key: 'all', text: 'Any time', value: 'all'},
                                         {key: '1d', text: 'Past 24 hours', value: '1d'},
                                         {key: '1w', text: 'Past week', value: '1w'},
                                         {key: '1m', text: 'Past month', value: '1m'},
                                         {key: '1y', text: 'Past year', value: '1y'},
                                     ]}/>
                    </Grid.Column>
                </Grid.Row>
                <Grid.Row>
                    <Grid.Column>
                        <Visibility continuous onBottomVisible={this.loadMore}>
                            <BaseJobList headers={headers} rows={rows} handleSort={this.handleSort}
                                         initialSort={'name'}/>
                        </Visibility>
                    </Grid.Column>
                </Grid.Row>
            </Grid>
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
                    orderBy: $orderBy,
                    search: $search,
                    timeRange: $timeRange
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
                $orderBy: String,
                $search: String,
                $timeRange: String
            ) {
              ...PublicJobList_data
            }
        `,

        getConnectionFromProps(props) {
            return props.data && props.data.publicBilbyJobs
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